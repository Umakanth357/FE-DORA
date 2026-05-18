export const TOOL_CATEGORIES = [
  {
    id: 'scm', label: 'SCM', title: 'Source Control', subtitle: 'Commits & Pull Requests',
    description: 'Extracts commits, PRs, and merge history — drives Lead Time and Deployment Frequency.',
    icon: '🔀', color: '#3b82f6',
    outputFile: 'scm_data.json',
    dora: ['Lead Time', 'Deployment Frequency'],
    tools: [
      { value: 'github',      label: 'GitHub' },
      { value: 'gitlab',      label: 'GitLab' },
      { value: 'bitbucket',   label: 'Bitbucket' },
      { value: 'azure_repos', label: 'Azure Repos' },
    ],
  },
  {
    id: 'cicd', label: 'CI/CD', title: 'Pipelines', subtitle: 'Builds & Deployments',
    description: 'Captures pipeline runs, deployment events — drives Deployment Frequency and Change Failure Rate.',
    icon: '⚡', color: '#f59e0b',
    outputFile: 'cicd_data.json',
    dora: ['Deployment Frequency', 'Change Failure Rate'],
    tools: [
      { value: 'jenkins',         label: 'Jenkins' },
      { value: 'github_actions',  label: 'GitHub Actions' },
      { value: 'gitlab_ci',       label: 'GitLab CI' },
      { value: 'circleci',        label: 'CircleCI' },
      { value: 'azure_pipelines', label: 'Azure Pipelines' },
    ],
  },
  {
    id: 'itsm', label: 'ITSM', title: 'Incidents', subtitle: 'Incidents & Recovery',
    description: 'Collects production incidents with auto-classification — drives Change Failure Rate and MTTR.',
    icon: '🚨', color: '#ef4444',
    outputFile: 'incidents_data.json',
    dora: ['Change Failure Rate', 'MTTR'],
    tools: [
      { value: 'servicenow', label: 'ServiceNow' },
      { value: 'jira',       label: 'Jira Service Mgmt' },
      { value: 'pagerduty',  label: 'PagerDuty' },
      { value: 'opsgenie',   label: 'Opsgenie' },
    ],
  },
]

export const DATE_RANGE_OPTIONS = [
  { value: 90,  label: 'Last 3 months' },
  { value: 180, label: 'Last 6 months', default: true },
  { value: 365, label: 'Last 12 months' },
]

export const BAND_META = {
  elite:             { label: 'Elite',  color: '#00e5c8', bg: 'rgba(0,229,200,0.12)' },
  high:              { label: 'High',   color: '#3b82f6', bg: 'rgba(59,130,246,0.12)' },
  medium:            { label: 'Medium', color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
  low:               { label: 'Low',    color: '#ef4444', bg: 'rgba(239,68,68,0.12)'  },
  insufficient_data: { label: 'No Data',color: '#6b7a99', bg: 'rgba(107,122,153,0.1)' },
}

export const METRIC_META = {
  deployment_frequency: {
    label: 'Deployment Frequency', icon: '🚀', unit: 'deploys/day',
    description: 'How often code ships to production',
    key: 'deploys_per_day', bandKey: 'band',
    thresholds: { elite: '≥1/day', high: '≥1/week', medium: '≥1/month', low: '<1/month' },
  },
  lead_time: {
    label: 'Lead Time for Changes', icon: '⏱', unit: 'hours (p50)',
    description: 'First commit → production deployment',
    key: 'p50_hrs', bandKey: 'band',
    thresholds: { elite: '<1h', high: '<1week', medium: '<1month', low: '>1month' },
  },
  change_failure_rate: {
    label: 'Change Failure Rate', icon: '💥', unit: '%',
    description: '% of deployments causing incidents',
    key: 'rate_pct', bandKey: 'band',
    thresholds: { elite: '≤5%', high: '≤10%', medium: '≤15%', low: '>15%' },
  },
  mttr: {
    label: 'Mean Time to Recovery', icon: '🔧', unit: 'hours (p50)',
    description: 'Time to recover from deployment failures',
    key: 'p50_hrs', bandKey: 'band',
    thresholds: { elite: '<1h', high: '<24h', medium: '<1week', low: '>1week' },
  },
}
