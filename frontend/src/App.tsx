import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Overview from './pages/Overview'
import Regions from './pages/Regions'
import Retailers from './pages/Retailers'
import Org from './pages/Org'
import Agent from './pages/Agent'
import FieldOps from './pages/FieldOps'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/regions" element={<Regions />} />
        <Route path="/retailers" element={<Retailers />} />
        <Route path="/org" element={<Org />} />
        <Route path="/agent" element={<Agent />} />
        <Route path="/field-ops" element={<FieldOps />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
