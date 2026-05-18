import { useState, useCallback, useRef, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts'
import { TOOL_CATEGORIES, DATE_RANGE_OPTIONS, BAND_META, METRIC_META } from './lib/config'
import { getProject, getDora, getTrends, getIncidents, uploadFile, downloadScript, reclassify, recompute } from './lib/api'

// ── Styles ───────────────────────────────────────────────────────────────────
const S = {
  page: { background:'#04080f', color:'#dde4f0', fontFamily:"'DM Sans',-apple-system,sans-serif",
          fontSize:14, minHeight:'100vh', lineHeight:1.7 },
  wrap: { maxWidth:1080, margin:'0 auto', padding:'0 32px 80px', position:'relative', zIndex:1 },
  card: { background:'rgba(255,255,255,0.03)', border:'1px solid rgba(255,255,255,0.07)',
          borderRadius:12, padding:'20px 24px' },
  btn: (primary) => ({
    padding: primary ? '11px 28px' : '9px 20px',
    borderRadius:9, border: primary ? '1px solid rgba(0,229,200,0.3)' : '1px solid rgba(255,255,255,0.1)',
    background: primary ? 'linear-gradient(135deg,#1a6b5a,#0d4f3f)' : 'rgba(255,255,255,0.05)',
    color: primary ? '#00e5c8' : '#8899b8', fontFamily:"'Syne',sans-serif",
    fontWeight:700, fontSize:13, cursor:'pointer', display:'inline-flex',
    alignItems:'center', gap:7, transition:'all 0.2s',
  }),
  input: { background:'rgba(255,255,255,0.05)', border:'1px solid rgba(255,255,255,0.15)',
           borderRadius:9, padding:'12px 16px', color:'#fff', fontSize:14,
           fontFamily:"'Syne',sans-serif", fontWeight:500, outline:'none' },
  select: { background:'rgba(0,0,0,0.4)', border:'1px solid rgba(255,255,255,0.12)',
            borderRadius:8, padding:'10px 14px', color:'#e2e8f0', fontSize:13,
            cursor:'pointer', outline:'none', appearance:'none' },
  label: { fontSize:10, fontFamily:"'DM Mono',monospace", fontWeight:600,
           letterSpacing:'0.15em', textTransform:'uppercase', color:'#6b7a99' },
  mono: { fontFamily:"'DM Mono',monospace" },
  sectionHead: { fontFamily:"'Syne',sans-serif", fontSize:22, fontWeight:800,
                 color:'#fff', letterSpacing:'-0.02em', marginBottom:20 },
}

// ── Band pill ─────────────────────────────────────────────────────────────────
function BandPill({ band, size = 'sm' }) {
  const m = BAND_META[band] || BAND_META.insufficient_data
  return (
    <span style={{
      display:'inline-block', padding: size==='lg' ? '5px 14px' : '3px 10px',
      borderRadius:20, background:m.bg, color:m.color,
      fontSize: size==='lg' ? 13 : 11, fontWeight:700, fontFamily:"'DM Mono',monospace",
      letterSpacing:'0.05em', border:`1px solid ${m.color}33`,
    }}>{m.label}</span>
  )
}

// ── Metric card ───────────────────────────────────────────────────────────────
function MetricCard({ metricKey, data }) {
  const meta  = METRIC_META[metricKey]
  const band  = data?.band || 'insufficient_data'
  const bm    = BAND_META[band]
  const value = data?.[meta.key]
  const fmt   = v => v == null ? '—' : metricKey === 'change_failure_rate' ? `${v}%` : `${v}`

  return (
    <div style={{
      ...S.card, borderTop:`2px solid ${bm.color}`,
      display:'flex', flexDirection:'column', gap:8,
    }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
        <div style={{ fontSize:20 }}>{meta.icon}</div>
        <BandPill band={band} />
      </div>
      <div style={{ fontSize:28, fontWeight:800, fontFamily:"'Syne',sans-serif",
                    color:bm.color, lineHeight:1 }}>
        {fmt(value)}
        <span style={{ fontSize:12, color:'#6b7a99', fontWeight:400,
                       marginLeft:6, fontFamily:"'DM Mono',monospace" }}>
          {value != null ? meta.unit : ''}
        </span>
      </div>
      <div style={{ fontSize:13, fontWeight:600, color:'#e2e8f0' }}>{meta.label}</div>
      <div style={{ fontSize:12, color:'#6b7a99' }}>{meta.description}</div>
      <div style={{ fontSize:11, fontFamily:"'DM Mono',monospace", color:'#4a5a7a',
                    borderTop:'1px solid rgba(255,255,255,0.06)', paddingTop:8, marginTop:4 }}>
        {Object.entries(meta.thresholds).map(([b,v]) => (
          <span key={b} style={{ marginRight:10, color: b===band ? bm.color : '#4a5a7a' }}>
            {BAND_META[b].label}: {v}
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Trend chart ───────────────────────────────────────────────────────────────
function TrendChart({ trends, metricKey }) {
  const keyMap = {
    deployment_frequency: 'deployments_success',
    lead_time:            'lead_time_p50_hrs',
    change_failure_rate:  'change_failure_rate',
    mttr:                 'mttr_p50_hrs',
  }
  const meta   = METRIC_META[metricKey]
  const dataKey = keyMap[metricKey]
  const color  = '#00e5c8'

  const data = (trends || [])
    .filter(r => r[dataKey] != null)
    .map(r => ({
      date:  r.metric_date?.slice(5),   // MM-DD
      value: metricKey === 'change_failure_rate'
               ? +(parseFloat(r[dataKey]) * 100).toFixed(2)
               : +(parseFloat(r[dataKey])).toFixed(2),
      band:  r[metricKey === 'deployment_frequency' ? 'df_band' :
               metricKey === 'lead_time'            ? 'lt_band' :
               metricKey === 'change_failure_rate'  ? 'cfr_band' : 'mttr_band'],
    }))

  if (!data.length) {
    return (
      <div style={{ height:120, display:'flex', alignItems:'center', justifyContent:'center',
                    color:'#4a5a7a', fontSize:13 }}>
        No trend data yet
      </div>
    )
  }

  return (
    <div>
      <div style={{ ...S.label, marginBottom:10 }}>{meta.label} — 90 day trend</div>
      <ResponsiveContainer width="100%" height={120}>
        <LineChart data={data} margin={{ top:5, right:10, bottom:0, left:0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
          <XAxis dataKey="date" tick={{ fill:'#4a5a7a', fontSize:10 }}
                 tickLine={false} axisLine={false} interval="preserveStartEnd" />
          <YAxis tick={{ fill:'#4a5a7a', fontSize:10 }}
                 tickLine={false} axisLine={false} width={40} />
          <Tooltip
            contentStyle={{ background:'#0c1220', border:'1px solid rgba(255,255,255,0.1)',
                            borderRadius:8, fontSize:12 }}
            labelStyle={{ color:'#6b7a99' }}
            itemStyle={{ color }}
            formatter={v => [`${v} ${meta.unit}`, meta.label]}
          />
          <Line type="monotone" dataKey="value" stroke={color}
                strokeWidth={2} dot={false} activeDot={{ r:4, fill:color }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── Incident review table ─────────────────────────────────────────────────────
function IncidentReviewTable({ projectId, onDone }) {
  const [incidents, setIncidents] = useState([])
  const [loading, setLoading]     = useState(true)
  const [selected, setSelected]   = useState(null)

  useEffect(() => {
    getIncidents(projectId, { needs_review: true, limit: 50 })
      .then(d => { setIncidents(d.incidents || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [projectId])

  const handleReclassify = async (incId, cls) => {
    await reclassify(incId, { classification: cls, reviewer: 'portal-user' })
    setIncidents(prev => prev.filter(i => i.id !== incId))
    onDone && onDone()
  }

  const cls_options = ['DEPLOYMENT_FAILURE','INFRASTRUCTURE','EXTERNAL_DEPENDENCY','SECURITY','OTHER']
  const cls_colors  = { DEPLOYMENT_FAILURE:'#ef4444', INFRASTRUCTURE:'#3b82f6',
                         EXTERNAL_DEPENDENCY:'#f59e0b', SECURITY:'#a78bfa', OTHER:'#6b7a99' }

  if (loading) return <div style={{ color:'#6b7a99', padding:20 }}>Loading...</div>
  if (!incidents.length) return (
    <div style={{ color:'#34d399', padding:20, textAlign:'center' }}>
      ✓ No incidents need review
    </div>
  )

  return (
    <div>
      <div style={{ ...S.label, marginBottom:12 }}>
        {incidents.length} incidents flagged for review
      </div>
      <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
        {incidents.map(inc => (
          <div key={inc.id} style={{
            ...S.card, padding:'14px 18px',
            border:'1px solid rgba(251,191,36,0.2)',
            background:'rgba(251,191,36,0.04)',
          }}>
            <div style={{ display:'flex', justifyContent:'space-between',
                          alignItems:'flex-start', gap:12 }}>
              <div style={{ flex:1 }}>
                <div style={{ fontSize:13, color:'#e2e8f0', fontWeight:500,
                              marginBottom:4 }}>{inc.title}</div>
                <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
                  <span style={{ ...S.mono, fontSize:11, color:'#6b7a99' }}>
                    {inc.external_id}
                  </span>
                  <span style={{ ...S.mono, fontSize:11,
                                 color: cls_colors[inc.classification] || '#6b7a99' }}>
                    Auto: {inc.classification} ({inc.classification_confidence}%)
                  </span>
                  {inc.severity && (
                    <span style={{ ...S.mono, fontSize:11, color:'#f59e0b' }}>
                      {inc.severity}
                    </span>
                  )}
                </div>
              </div>
              <div style={{ display:'flex', gap:6, flexWrap:'wrap', flexShrink:0 }}>
                {cls_options.map(cls => (
                  <button key={cls} onClick={() => handleReclassify(inc.id, cls)}
                    style={{
                      padding:'4px 10px', borderRadius:6, fontSize:10, fontWeight:700,
                      fontFamily:"'DM Mono',monospace", cursor:'pointer',
                      background: cls === 'DEPLOYMENT_FAILURE'
                                  ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.05)',
                      border:`1px solid ${cls_colors[cls] || '#333'}44`,
                      color: cls_colors[cls] || '#6b7a99',
                    }}>
                    {cls === 'DEPLOYMENT_FAILURE' ? '🔴 Deploy Fail' :
                     cls === 'INFRASTRUCTURE'     ? '🔵 Infra'       :
                     cls === 'EXTERNAL_DEPENDENCY'? '🟡 External'    :
                     cls === 'SECURITY'           ? '🟣 Security'    : '⚫ Other'}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
function Dashboard({ projectId, onBack }) {
  const [dora,    setDora]    = useState(null)
  const [trends,  setTrends]  = useState([])
  const [loading, setLoading] = useState(true)
  const [tab,     setTab]     = useState('overview')
  const [recomputing, setRecomputing] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([
      getDora(projectId, 90),
      getTrends(projectId, 90),
    ]).then(([d, t]) => {
      setDora(d); setTrends(t.trend || [])
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [projectId])

  useEffect(() => { load() }, [load])

  const handleRecompute = async () => {
    setRecomputing(true)
    await recompute(projectId)
    await load()
    setRecomputing(false)
  }

  const metrics = dora?.metrics || {}
  const overall = dora?.overall_band

  const TABS = [
    { id:'overview',  label:'Overview'  },
    { id:'trends',    label:'Trends'    },
    { id:'incidents', label:'Incidents' },
  ]

  return (
    <div>
      {/* Header */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
                    marginBottom:32, flexWrap:'wrap', gap:12 }}>
        <div>
          <button onClick={onBack}
            style={{ ...S.btn(false), marginBottom:10, padding:'6px 14px', fontSize:12 }}>
            ← All Projects
          </button>
          <div style={{ fontFamily:"'Syne',sans-serif", fontSize:28, fontWeight:800,
                        color:'#fff', letterSpacing:'-0.02em' }}>
            {projectId}
            {overall && <BandPill band={overall} size="lg" />}
          </div>
          <div style={{ fontSize:13, color:'#6b7a99', marginTop:4 }}>
            {dora?.window_start} → {dora?.window_end}
            <span style={{ marginLeft:12, ...S.mono, fontSize:11, color:'#4a5a7a' }}>
              {dora?.window_days}d window
            </span>
          </div>
        </div>
        <button onClick={handleRecompute} disabled={recomputing} style={S.btn(true)}>
          {recomputing ? '⟳ Recomputing…' : '⟳ Recompute Metrics'}
        </button>
      </div>

      {/* Tabs */}
      <div style={{ display:'flex', gap:4, marginBottom:28,
                    borderBottom:'1px solid rgba(255,255,255,0.07)', paddingBottom:0 }}>
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            padding:'8px 20px', borderRadius:'8px 8px 0 0',
            background: tab===t.id ? 'rgba(0,229,200,0.08)' : 'transparent',
            border: tab===t.id ? '1px solid rgba(0,229,200,0.2)' : '1px solid transparent',
            borderBottom: tab===t.id ? '2px solid #00e5c8' : '2px solid transparent',
            color: tab===t.id ? '#00e5c8' : '#6b7a99',
            fontFamily:"'DM Mono',monospace", fontSize:12, fontWeight:600,
            cursor:'pointer', letterSpacing:'0.05em',
          }}>{t.label}</button>
        ))}
      </div>

      {loading ? (
        <div style={{ color:'#6b7a99', textAlign:'center', padding:60 }}>
          Computing DORA metrics…
        </div>
      ) : tab === 'overview' ? (
        <div>
          {/* 4 metric cards */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(240px,1fr))',
                        gap:14, marginBottom:28 }}>
            {Object.entries(METRIC_META).map(([key]) => (
              <MetricCard key={key} metricKey={key} data={metrics[key]} />
            ))}
          </div>

          {/* Classification breakdown */}
          {metrics.change_failure_rate?.total_deployments > 0 && (
            <div style={{ ...S.card }}>
              <div style={{ ...S.label, marginBottom:12 }}>Change Failure Rate Breakdown</div>
              <div style={{ display:'flex', gap:24, flexWrap:'wrap' }}>
                <div>
                  <div style={{ fontSize:24, fontWeight:800, fontFamily:"'Syne',sans-serif",
                                color:'#e2e8f0' }}>
                    {metrics.change_failure_rate.total_deployments}
                  </div>
                  <div style={{ fontSize:12, color:'#6b7a99' }}>Total deployments</div>
                </div>
                <div>
                  <div style={{ fontSize:24, fontWeight:800, fontFamily:"'Syne',sans-serif",
                                color:'#ef4444' }}>
                    {metrics.change_failure_rate.failed_deployments}
                  </div>
                  <div style={{ fontSize:12, color:'#6b7a99' }}>Caused incidents</div>
                </div>
                <div>
                  <div style={{ fontSize:24, fontWeight:800, fontFamily:"'Syne',sans-serif",
                                color:'#6b7a99', fontSize:13 }}>
                    ℹ Only deployment-failure incidents count.<br/>
                    Infra / vendor / security excluded by classifier.
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : tab === 'trends' ? (
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
          {Object.keys(METRIC_META).map(key => (
            <div key={key} style={S.card}>
              <TrendChart trends={trends} metricKey={key} />
            </div>
          ))}
        </div>
      ) : (
        <IncidentReviewTable projectId={projectId} onDone={load} />
      )}
    </div>
  )
}

// ── Upload Portal ─────────────────────────────────────────────────────────────
function UploadPortal({ onProjectReady }) {
  const [projectId,  setProjectId]  = useState('')
  const [projectInfo,setProjectInfo]= useState(null)
  const [days,       setDays]       = useState(180)
  const [ready,      setReady]      = useState(false)
  const [configuring,setConfiguring]= useState(false)
  const [files,      setFiles]      = useState([])
  const [uploading,  setUploading]  = useState(false)
  const [progress,   setProgress]   = useState(0)
  const [results,    setResults]    = useState([])
  const [done,       setDone]       = useState(false)
  const [selectedTools, setSelectedTools] = useState({})
  const fileRef = useRef()

  const configure = async () => {
    if (!projectId.trim()) return
    setConfiguring(true)
    const pid = projectId.trim().toLowerCase().replace(/[^a-z0-9_-]/g,'-')
    setProjectId(pid)
    try { setProjectInfo(await getProject(pid)) } catch { setProjectInfo({ exists:false }) }
    setReady(true); setConfiguring(false)
    setTimeout(() => document.getElementById('tools-section')?.scrollIntoView({ behavior:'smooth' }), 100)
  }

  const addFiles = useCallback(newFiles => {
    setFiles(prev => {
      const existing = new Set(prev.map(f => f.name))
      return [...prev, ...newFiles.filter(f => f.name.endsWith('.json') && !existing.has(f.name))]
    })
  }, [])

  const submit = async () => {
    if (!files.length || uploading) return
    setUploading(true); setProgress(0)
    const res = []
    for (const file of files) {
      try { res.push(await uploadFile(file, setProgress)) }
      catch (e) { res.push({ error: true, file: file.name,
                              message: e.response?.data?.detail || e.message }) }
    }
    setResults(res); setUploading(false); setDone(true)
  }

  if (done) return (
    <div style={{ maxWidth:680, margin:'0 auto', animation:'fadeUp 0.4s ease' }}>
      <div style={{ ...S.card, border:'1px solid rgba(0,229,200,0.25)',
                    background:'rgba(0,229,200,0.04)', marginBottom:20 }}>
        <div style={{ fontSize:32, marginBottom:12 }}>✅</div>
        <div style={{ fontFamily:"'Syne',sans-serif", fontSize:22, fontWeight:800,
                      color:'#fff', marginBottom:8 }}>Data ingested successfully</div>
        {results.map((r,i) => (
          <div key={i} style={{ background:'rgba(0,0,0,0.2)', borderRadius:8,
                                padding:'10px 14px', marginBottom:8 }}>
            {r.error ? (
              <div style={{ color:'#ef4444', fontSize:13 }}>✗ {r.file}: {r.message}</div>
            ) : (
              <div>
                <div style={{ ...S.mono, fontSize:12, color:'#00e5c8', marginBottom:4 }}>
                  {r.data_type?.toUpperCase()} · {r.project_id} · {r.duration_ms}ms
                </div>
                <div style={{ display:'flex', gap:16, flexWrap:'wrap' }}>
                  {Object.entries(r.inserted||{}).map(([k,v]) => (
                    <span key={k} style={{ fontSize:12, color:'#6b7a99' }}>
                      <span style={{ color:'#e2e8f0', fontWeight:600 }}>{v}</span> {k}
                    </span>
                  ))}
                  {r.skipped > 0 && (
                    <span style={{ fontSize:12, color:'#f59e0b' }}>
                      {r.skipped} skipped
                    </span>
                  )}
                </div>
                {r.classification_summary?.total > 0 && (
                  <div style={{ marginTop:8, fontSize:12, color:'#6b7a99' }}>
                    Incidents: {r.classification_summary.dora_relevant} DORA-relevant,{' '}
                    {r.classification_summary.excluded} excluded (infra/vendor/security),{' '}
                    {r.classification_summary.needs_review} flagged for review
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        <button onClick={() => onProjectReady(projectId)} style={{ ...S.btn(true), marginTop:16, width:'100%', justifyContent:'center' }}>
          View DORA Dashboard →
        </button>
      </div>
      <button onClick={() => { setDone(false); setResults([]); setFiles([]) }}
        style={{ ...S.btn(false) }}>← Upload more data</button>
    </div>
  )

  return (
    <div>
      {/* Hero */}
      <div style={{ textAlign:'center', padding:'56px 0 48px', animation:'fadeUp 0.7s ease' }}>
        {/* Logo */}
        <div style={{ display:'flex', alignItems:'center', justifyContent:'center',
                      gap:10, marginBottom:32 }}>
          <div style={{ width:34, height:34, borderRadius:8, border:'1.5px solid #c8a96e',
                        display:'flex', alignItems:'center', justifyContent:'center' }}>
            <div style={{ width:12, height:12, borderRadius:'50%', background:'#c8a96e' }}/>
          </div>
          <span style={{ fontFamily:"'Syne',sans-serif", fontSize:12, fontWeight:700,
                         letterSpacing:'0.2em', textTransform:'uppercase', color:'#c8a96e' }}>
            Velocity Intelligence
          </span>
        </div>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'center', gap:8,
                      fontSize:11, fontFamily:"'DM Mono',monospace", letterSpacing:'0.25em',
                      textTransform:'uppercase', color:'#00e5c8', marginBottom:18 }}>
          <span style={{ width:32, height:1, background:'#00e5c8', opacity:0.5 }}/>
          DORA Metrics Platform
          <span style={{ width:32, height:1, background:'#00e5c8', opacity:0.5 }}/>
        </div>
        <h1 style={{ fontFamily:"'Syne',sans-serif", fontSize:'clamp(38px,7vw,68px)',
                     fontWeight:800, lineHeight:1.02, letterSpacing:'-0.03em',
                     color:'#fff', marginBottom:18 }}>
          Measure What<br/>
          <span style={{ background:'linear-gradient(135deg,#e8c98e,#c8a96e,#a07840)',
                         WebkitBackgroundClip:'text', WebkitTextFillColor:'transparent' }}>
            Actually Ships
          </span>
        </h1>
        <p style={{ fontSize:16, fontWeight:300, color:'#6b7a99',
                    maxWidth:480, margin:'0 auto 40px', lineHeight:1.7 }}>
          Run one script per tool. Upload the output. Get accurate DORA metrics — with intelligent incident classification built in.
        </p>

        {/* Project input */}
        <div style={{ maxWidth:560, margin:'0 auto' }}>
          <div style={{ ...S.label, marginBottom:8, textAlign:'left' }}>Project Name</div>
          <div style={{ display:'flex', gap:10, marginBottom:10 }}>
            <input value={projectId} onChange={e => setProjectId(e.target.value)}
              onKeyDown={e => e.key==='Enter' && configure()}
              placeholder="e.g. payments-service, mobile-app…"
              style={{ ...S.input, flex:1 }}/>
            <select value={days} onChange={e => setDays(Number(e.target.value))} style={S.select}>
              {DATE_RANGE_OPTIONS.map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <button onClick={configure} disabled={configuring||!projectId.trim()} style={S.btn(true)}>
              {configuring ? '…' : '→ Configure'}
            </button>
          </div>
          {ready && projectInfo && (
            <div style={{ display:'flex', alignItems:'center', gap:10, padding:'10px 14px',
                          background: projectInfo.exists ? 'rgba(0,229,200,0.06)' : 'rgba(200,169,110,0.06)',
                          border:`1px solid ${projectInfo.exists ? 'rgba(0,229,200,0.2)' : 'rgba(200,169,110,0.2)'}`,
                          borderRadius:8 }}>
              <div style={{ width:7, height:7, borderRadius:'50%',
                            background: projectInfo.exists ? '#00e5c8' : '#c8a96e' }}/>
              <span style={{ fontSize:13, color: projectInfo.exists ? '#00e5c8' : '#c8a96e' }}>
                {projectInfo.exists
                  ? <>Resuming <b style={{ color:'#fff' }}>{projectId}</b> — last ingestion: {projectInfo.last_ingestion ? new Date(projectInfo.last_ingestion).toLocaleDateString() : 'never'}</>
                  : <>New project <b style={{ color:'#fff' }}>{projectId}</b> — will be created on first upload</>}
              </span>
              {projectInfo.exists && projectInfo.latest_dora?.overall && (
                <BandPill band={projectInfo.latest_dora.overall} />
              )}
            </div>
          )}
        </div>
      </div>

      {/* Tool cards */}
      {ready && (
        <div id="tools-section">
          <div style={{ marginBottom:24 }}>
            <div style={S.sectionHead}>Select Your Tools</div>
            <div style={{ color:'#6b7a99', fontSize:13, marginTop:-14 }}>
              Pick your tool in each category → download the script → run it → upload the JSON
            </div>
          </div>

          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(300px,1fr))',
                        gap:14, marginBottom:48 }}>
            {TOOL_CATEGORIES.map(cat => (
              <ToolCard key={cat.id} category={cat} project={projectId} days={days}
                onSelect={tool => setSelectedTools(p => ({...p, [cat.id]:tool}))} />
            ))}
          </div>

          {/* Upload zone */}
          <div style={{ marginBottom:12, ...S.sectionHead }}>Upload Output Files</div>
          <UploadZone files={files} onAdd={addFiles}
            onRemove={i => setFiles(p => p.filter((_,idx) => idx!==i))} />
          {uploading && (
            <div style={{ height:3, background:'rgba(255,255,255,0.06)',
                          borderRadius:2, margin:'12px 0' }}>
              <div style={{ height:'100%', background:'#00e5c8', borderRadius:2,
                            width:`${progress}%`, transition:'width 0.3s' }}/>
            </div>
          )}
          <div style={{ display:'flex', justifyContent:'flex-end', alignItems:'center',
                        gap:16, marginTop:16 }}>
            <span style={{ fontSize:12, color:'#4a5a7a' }}>
              {files.length ? `${files.length} file${files.length>1?'s':''} ready` : 'Upload at least one file'}
            </span>
            <button onClick={submit} disabled={!files.length||uploading} style={{
              ...S.btn(true),
              opacity: files.length&&!uploading ? 1 : 0.4,
              cursor: files.length&&!uploading ? 'pointer' : 'not-allowed',
              background:'linear-gradient(135deg,#b8914a,#8a6830)',
              border:'1px solid rgba(200,169,110,0.4)', color:'#fff',
            }}>
              {uploading ? '⟳ Ingesting…' : 'Ingest into DORA →'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Tool Card ─────────────────────────────────────────────────────────────────
function ToolCard({ category, project, days, onSelect }) {
  const [tool, setTool] = useState('')
  const [downloading, setDownloading] = useState(false)

  const handleDownload = async () => {
    if (!tool) return
    setDownloading(true)
    try { await downloadScript(tool, project, days) }
    catch { alert('Download failed — is the backend running?') }
    finally { setDownloading(false) }
  }

  const instructions = {
    github:         'Create a Fine-grained PAT: Contents (read), Pull requests (read)',
    gitlab:         'Create a Personal Access Token with read_api scope',
    bitbucket:      'Create an App Password: Repositories: Read, Pull Requests: Read',
    azure_repos:    'Create a PAT: Code (read), Pull Request Threads (read)',
    jenkins:        'Go to your user → Configure → API Token → Add new Token',
    github_actions: 'Reuse GitHub PAT or create one with Actions: Read scope',
    gitlab_ci:      'Reuse GitLab token with read_api scope',
    circleci:       'User Settings → Personal API Tokens → Create New Token',
    azure_pipelines:'Create PAT: Build (read), Release (read)',
    servicenow:     'Create user with itil role — use dedicated API service account',
    jira:           'Atlassian Account → Security → API Tokens → Create API Token',
    pagerduty:      'Integrations → API Access Keys → Create New Key (read-only)',
    opsgenie:       'Settings → API Key Management → Add API Key (read)',
  }

  return (
    <div style={{
      ...S.card,
      borderTop:`2px solid ${tool ? category.color : 'transparent'}`,
      boxShadow: tool ? `0 0 20px ${category.color}18` : 'none',
      transition:'all 0.25s',
    }}>
      <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:10 }}>
        <div style={{ width:42, height:42, borderRadius:10, fontSize:20,
                      background:`${category.color}18`,
                      display:'flex', alignItems:'center', justifyContent:'center' }}>
          {category.icon}
        </div>
        <div>
          <div style={{ ...S.mono, fontSize:10, color:category.color,
                        fontWeight:700, letterSpacing:'0.15em', textTransform:'uppercase' }}>
            {category.label}
          </div>
          <div style={{ fontFamily:"'Syne',sans-serif", fontSize:15, fontWeight:700, color:'#fff' }}>
            {category.title}
          </div>
        </div>
      </div>
      <p style={{ fontSize:12, color:'#7a8eaa', marginBottom:14, lineHeight:1.6 }}>
        {category.description}
      </p>
      <div style={{ display:'flex', gap:6, marginBottom:14 }}>
        {category.dora.map(d => (
          <span key={d} style={{ ...S.mono, fontSize:10, padding:'2px 7px', borderRadius:4,
                                  background:`${category.color}18`, color:category.color,
                                  border:`1px solid ${category.color}33` }}>{d}</span>
        ))}
      </div>
      <div style={{ ...S.label, marginBottom:6 }}>Select Tool</div>
      <select value={tool} onChange={e => { setTool(e.target.value); onSelect(e.target.value) }}
        style={{ ...S.select, width:'100%', marginBottom:tool?12:0 }}>
        <option value="">— Select your {category.label} tool —</option>
        {category.tools.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
      </select>

      {tool && (
        <div style={{ background:'rgba(0,0,0,0.3)', border:'1px solid rgba(255,255,255,0.07)',
                      borderRadius:9, padding:'12px 14px' }}>
          <div style={{ fontSize:12, color:'#6b7a99', marginBottom:8, lineHeight:1.6 }}>
            <span style={{ color:'#fbbf24', fontWeight:600 }}>Token required: </span>
            {instructions[tool] || 'Create a read-only API token'}
          </div>
          <div style={{ ...S.mono, fontSize:11, color:'#4a5a7a', marginBottom:10 }}>
            python collect_{tool}.py --token YOUR_TOKEN --project {project||'your-project'} --days {days}
          </div>
          <button onClick={handleDownload} disabled={downloading} style={{
            ...S.btn(true), width:'100%', justifyContent:'center',
            background:`linear-gradient(135deg,${category.color}22,${category.color}11)`,
            border:`1px solid ${category.color}44`, color:category.color,
          }}>
            {downloading ? '⟳ Downloading…' : `⬇ Download collect_${tool}.py`}
          </button>
        </div>
      )}
    </div>
  )
}

// ── Upload Zone ───────────────────────────────────────────────────────────────
function UploadZone({ files, onAdd, onRemove }) {
  const [drag, setDrag] = useState(false)
  const ref = useRef()
  const icon = n => n.includes('scm')?'🔀':n.includes('cicd')?'⚡':'🚨'

  return (
    <div>
      <div onClick={() => ref.current?.click()}
        onDragOver={e=>{e.preventDefault();setDrag(true)}}
        onDragLeave={()=>setDrag(false)}
        onDrop={e=>{e.preventDefault();setDrag(false);onAdd(Array.from(e.dataTransfer.files))}}
        style={{
          border:`1.5px dashed ${drag?'#00e5c8':'rgba(255,255,255,0.12)'}`,
          borderRadius:14, padding:'32px 24px', textAlign:'center', cursor:'pointer',
          background: drag?'rgba(0,229,200,0.04)':'rgba(255,255,255,0.015)',
          transition:'all 0.2s',
        }}>
        <div style={{ fontSize:32, marginBottom:10 }}>📁</div>
        <div style={{ fontSize:14, fontWeight:600, color:'#fff', marginBottom:6 }}>
          Drop JSON files here or <span style={{ color:'#00e5c8' }}>click to browse</span>
        </div>
        <div style={{ display:'flex', gap:8, justifyContent:'center', flexWrap:'wrap' }}>
          {['scm_data.json','cicd_data.json','incidents_data.json'].map(f => (
            <span key={f} style={{ ...S.mono, fontSize:11, padding:'2px 8px', borderRadius:4,
                                    background:'rgba(255,255,255,0.06)',
                                    border:'1px solid rgba(255,255,255,0.08)', color:'#6b7a99' }}>
              {f}
            </span>
          ))}
        </div>
        <input ref={ref} type="file" multiple accept=".json" style={{ display:'none' }}
          onChange={e => onAdd(Array.from(e.target.files))}/>
      </div>
      {files.length > 0 && (
        <div style={{ marginTop:12, display:'flex', flexDirection:'column', gap:8 }}>
          {files.map((f,i) => (
            <div key={i} style={{ display:'flex', alignItems:'center', gap:10,
                                   padding:'10px 16px',
                                   background:'rgba(0,229,200,0.05)',
                                   border:'1px solid rgba(0,229,200,0.15)',
                                   borderRadius:8 }}>
              <span style={{ fontSize:18 }}>{icon(f.name)}</span>
              <div style={{ flex:1 }}>
                <div style={{ fontSize:13, fontWeight:500, color:'#fff' }}>{f.name}</div>
                <div style={{ fontSize:11, color:'#6b7a99' }}>{(f.size/1024).toFixed(1)} KB</div>
              </div>
              <button onClick={() => onRemove(i)} style={{
                width:24, height:24, borderRadius:'50%', border:'1px solid rgba(239,68,68,0.3)',
                background:'rgba(239,68,68,0.1)', color:'#f87171', cursor:'pointer', fontSize:11,
              }}>✕</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Project List ──────────────────────────────────────────────────────────────
function ProjectList({ onSelect, onNew }) {
  const [projects, setProjects] = useState([])
  const [loading,  setLoading]  = useState(true)

  useEffect(() => {
    import('./lib/api').then(({ listProjects }) =>
      listProjects().then(d => { setProjects(d.projects||[]); setLoading(false) })
    ).catch(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ color:'#6b7a99', textAlign:'center', padding:40 }}>Loading…</div>
  if (!projects.length) return null

  return (
    <div style={{ marginBottom:40 }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center',
                    marginBottom:16 }}>
        <div style={S.sectionHead}>Your Projects</div>
        <button onClick={onNew} style={S.btn(true)}>+ New Project</button>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(280px,1fr))', gap:12 }}>
        {projects.map(p => (
          <div key={p.id} onClick={() => onSelect(p.id)} style={{
            ...S.card, cursor:'pointer', transition:'all 0.2s',
          }} onMouseEnter={e=>e.currentTarget.style.borderColor='rgba(255,255,255,0.15)'}
             onMouseLeave={e=>e.currentTarget.style.borderColor='rgba(255,255,255,0.07)'}>
            <div style={{ display:'flex', justifyContent:'space-between',
                          alignItems:'flex-start', marginBottom:8 }}>
              <div style={{ fontFamily:"'Syne',sans-serif", fontSize:15,
                            fontWeight:700, color:'#fff' }}>{p.display_name}</div>
              {p.latest_dora?.overall && <BandPill band={p.latest_dora.overall} />}
            </div>
            <div style={{ display:'flex', gap:16, flexWrap:'wrap' }}>
              {[
                ['commits',     p.record_counts?.commits],
                ['deployments', p.record_counts?.deployments],
                ['incidents',   p.record_counts?.incidents],
              ].map(([k,v]) => (
                <div key={k}>
                  <span style={{ fontSize:16, fontWeight:700, color:'#e2e8f0',
                                 fontFamily:"'Syne',sans-serif" }}>{v||0}</span>
                  <span style={{ fontSize:11, color:'#6b7a99', marginLeft:4 }}>{k}</span>
                </div>
              ))}
            </div>
            {p.record_counts?.needs_review > 0 && (
              <div style={{ marginTop:8, fontSize:11, color:'#fbbf24',
                            fontFamily:"'DM Mono',monospace" }}>
                ⚠ {p.record_counts.needs_review} incidents need review
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Root App ──────────────────────────────────────────────────────────────────
export default function App() {
  const [view,      setView]      = useState('home')  // home | upload | dashboard
  const [activeProject, setActiveProject] = useState(null)

  return (
    <div style={S.page}>
      <style>{`
        @keyframes fadeUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}
        select option{background:#0d1420}
        *{box-sizing:border-box}
        ::-webkit-scrollbar{width:6px}
        ::-webkit-scrollbar-track{background:#0c1220}
        ::-webkit-scrollbar-thumb{background:#2a3450;border-radius:3px}
      `}</style>

      {/* Background */}
      <div style={{ position:'fixed', inset:0, zIndex:0, pointerEvents:'none', overflow:'hidden' }}>
        <div style={{ position:'absolute', width:700, height:700, borderRadius:'50%',
                      background:'#0d4f8a', filter:'blur(120px)', opacity:0.12,
                      top:-200, right:-100 }}/>
        <div style={{ position:'absolute', width:500, height:500, borderRadius:'50%',
                      background:'#00897b', filter:'blur(120px)', opacity:0.10,
                      bottom:100, left:-150 }}/>
        <div style={{ position:'absolute', inset:0,
                      backgroundImage:'linear-gradient(rgba(255,255,255,0.016) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.016) 1px,transparent 1px)',
                      backgroundSize:'60px 60px' }}/>
      </div>

      <div style={S.wrap}>
        {view === 'dashboard' && activeProject ? (
          <Dashboard projectId={activeProject} onBack={() => setView('home')} />
        ) : view === 'upload' ? (
          <UploadPortal onProjectReady={pid => {
            setActiveProject(pid); setView('dashboard')
          }} />
        ) : (
          <div>
            <ProjectList
              onSelect={pid => { setActiveProject(pid); setView('dashboard') }}
              onNew={() => setView('upload')}
            />
            {/* Show upload portal inline if no projects yet */}
            <UploadPortal onProjectReady={pid => {
              setActiveProject(pid); setView('dashboard')
            }} />
          </div>
        )}
      </div>
    </div>
  )
}
