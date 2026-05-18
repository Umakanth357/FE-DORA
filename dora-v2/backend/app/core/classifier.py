"""
Incident Classification Engine
Classifies incidents into DORA-relevant buckets before storage.
Only DEPLOYMENT_FAILURE incidents count toward CFR and MTTR.
"""
from dataclasses import dataclass
from typing import Optional

_DEPLOY_KW = frozenset([
    "deploy","deployment","release","rollout","pushed","upgrade","update",
    "migration","config change","configuration change","hotfix","patch",
    "regression","after release","post deploy","post-deploy","after deploy",
    "new version","went live","broke after","broke following",
    "change management","change request","cr-","feature flag","rollback",
])
_INFRA_KW = frozenset([
    "cpu","memory","ram","disk","storage","network","dns","ssl","certificate",
    "tls","hardware","datacenter","aws","azure","gcp","cloud provider",
    "server","host","node","pod","kubernetes","k8s","capacity","quota",
    "throttl","bandwidth","latency spike","packet loss","firewall",
    "load balancer","database server","db server",
])
_EXTERNAL_KW = frozenset([
    "vendor","third party","third-party","external","upstream",
    "payment gateway","stripe","twilio","sendgrid","provider",
    "dependency","sla breach","partner","cdn","cloudflare","akamai","fastly",
])
_SECURITY_KW = frozenset([
    "security","breach","unauthorized","attack","vulnerability","exploit",
    "intrusion","phishing","credential","ddos","dos","ransomware","malware",
    "data leak","exposure","cve-",
])
_CATEGORY_MAP = {
    "software":"DEPLOYMENT_FAILURE","application":"DEPLOYMENT_FAILURE",
    "release":"DEPLOYMENT_FAILURE","deployment":"DEPLOYMENT_FAILURE",
    "change":"DEPLOYMENT_FAILURE","code":"DEPLOYMENT_FAILURE",
    "configuration":"DEPLOYMENT_FAILURE",
    "hardware":"INFRASTRUCTURE","network":"INFRASTRUCTURE",
    "storage":"INFRASTRUCTURE","cloud":"INFRASTRUCTURE",
    "infrastructure":"INFRASTRUCTURE","database":"INFRASTRUCTURE",
    "capacity":"INFRASTRUCTURE",
    "vendor":"EXTERNAL_DEPENDENCY","third-party":"EXTERNAL_DEPENDENCY",
    "external":"EXTERNAL_DEPENDENCY",
    "security":"SECURITY",
    "access":"OTHER","user access":"OTHER",
    "service request":"OTHER","facilities":"OTHER",
}
_DEPLOY_LABELS = frozenset([
    "deployment","release","regression","post-deploy","code-change",
    "config-change","feature-flag","rollback",
])


@dataclass
class ClassificationResult:
    classification:  str
    confidence:      int
    dora_relevant:   bool
    cfr_include:     bool
    mttr_include:    bool
    needs_review:    bool
    reasons:         list[str]


def classify_incident(
    title:             str,
    description:       str                = "",
    category:          str                = "",
    labels:            Optional[list[str]] = None,
    change_request_id: Optional[str]       = None,
    deployment_id:     Optional[str]       = None,
    service_affected:  Optional[str]       = None,
    confidence_threshold: int              = 40,
) -> ClassificationResult:
    labels = labels or []
    text = " ".join([title, description, service_affected or ""]).lower()

    scores = {
        "DEPLOYMENT_FAILURE": 0, "INFRASTRUCTURE": 0,
        "EXTERNAL_DEPENDENCY": 0, "SECURITY": 0, "OTHER": 0,
    }
    reasons = []

    # Signal 1: Explicit links (strongest)
    if deployment_id:
        scores["DEPLOYMENT_FAILURE"] += 80
        reasons.append(f"explicit deployment link: {deployment_id}")
    if change_request_id:
        scores["DEPLOYMENT_FAILURE"] += 70
        reasons.append(f"change request: {change_request_id}")

    # Signal 2: ITSM category
    cat_lower = (category or "").lower().strip()
    for key, bucket in _CATEGORY_MAP.items():
        if key in cat_lower:
            scores[bucket] += 50
            reasons.append(f"category '{category}' → {bucket}")
            break

    # Signal 3: Labels
    for label in labels:
        if label.lower() in _DEPLOY_LABELS:
            scores["DEPLOYMENT_FAILURE"] += 20
            reasons.append(f"label: '{label}'")

    # Signal 4: Keywords
    d_kw = [kw for kw in _DEPLOY_KW    if kw in text]
    i_kw = [kw for kw in _INFRA_KW     if kw in text]
    e_kw = [kw for kw in _EXTERNAL_KW  if kw in text]
    s_kw = [kw for kw in _SECURITY_KW  if kw in text]

    scores["DEPLOYMENT_FAILURE"]  += len(d_kw) * 10
    scores["INFRASTRUCTURE"]      += len(i_kw) * 10
    scores["EXTERNAL_DEPENDENCY"] += len(e_kw) * 10
    scores["SECURITY"]            += len(s_kw) * 15

    if d_kw: reasons.append(f"keywords: {d_kw[:3]}")
    if i_kw: reasons.append(f"infra kw: {i_kw[:2]}")
    if e_kw: reasons.append(f"external kw: {e_kw[:2]}")
    if s_kw: reasons.append(f"security kw: {s_kw[:2]}")

    if max(scores.values()) < 10:
        scores["OTHER"] = 50
        reasons.append("no signals — defaulting to OTHER")

    best       = max(scores, key=scores.get)
    confidence = min(100, scores[best])
    dora       = best == "DEPLOYMENT_FAILURE"
    cfr        = dora and confidence >= confidence_threshold
    review     = confidence < confidence_threshold or (dora and not deployment_id and not change_request_id and not d_kw)

    return ClassificationResult(
        classification  = best,
        confidence      = confidence,
        dora_relevant   = dora,
        cfr_include     = cfr,
        mttr_include    = dora,
        needs_review    = review,
        reasons         = reasons[:5],
    )


def classify_batch(incidents: list[dict], threshold: int = 40) -> list[dict]:
    out = []
    for inc in incidents:
        r = classify_incident(
            title              = inc.get("title", ""),
            description        = inc.get("description", ""),
            category           = inc.get("category", ""),
            labels             = inc.get("labels", []),
            change_request_id  = inc.get("change_request_id"),
            deployment_id      = inc.get("related_deployment_id"),
            service_affected   = inc.get("service_affected"),
            confidence_threshold = threshold,
        )
        out.append({**inc,
            "_classification": r.classification,
            "_confidence":     r.confidence,
            "_dora_relevant":  r.dora_relevant,
            "_cfr_include":    r.cfr_include,
            "_needs_review":   r.needs_review,
            "_reasons":        r.reasons,
        })
    return out
