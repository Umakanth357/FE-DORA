import axios from 'axios'

const api = axios.create({ baseURL: '' })

export const getProject  = (id)      => api.get(`/api/projects/${id}`).then(r => r.data)
export const listProjects = ()        => api.get('/api/projects').then(r => r.data)
export const getDora     = (id, days) => api.get(`/api/projects/${id}/dora`, { params: { window_days: days } }).then(r => r.data)
export const getTrends   = (id, days) => api.get(`/api/projects/${id}/trends`, { params: { days } }).then(r => r.data)
export const getIncidents = (id, params) => api.get(`/api/projects/${id}/incidents`, { params }).then(r => r.data)
export const reclassify  = (incId, body) => api.post(`/api/incidents/${incId}/reclassify`, body).then(r => r.data)
export const recompute   = (id)      => api.post(`/api/projects/${id}/recompute`).then(r => r.data)

export const uploadFile = (file, onProgress) => {
  const form = new FormData()
  form.append('file', file)
  return api.post('/api/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: e => onProgress && onProgress(Math.round(e.loaded * 100 / e.total))
  }).then(r => r.data)
}

export const downloadScript = async (tool, project, days) => {
  const res = await api.get(`/api/scripts/${tool}`, {
    params: { project, days }, responseType: 'blob'
  })
  const url = URL.createObjectURL(new Blob([res.data]))
  const a = document.createElement('a')
  a.href = url; a.download = `collect_${tool}.py`; a.click()
  URL.revokeObjectURL(url)
}
