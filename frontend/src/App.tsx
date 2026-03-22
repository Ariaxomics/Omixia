import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import ProtectedRoute from './components/ProtectedRoute'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import SamplesPage from './pages/SamplesPage'
import SampleDetailPage from './pages/SampleDetailPage'
import KnowledgePage from './pages/KnowledgePage'
import LabDashboardPage from './pages/LabDashboardPage'
import GapAnalysisPage from './pages/GapAnalysisPage'
import CohortPage from './pages/CohortPage'
import UsersPage from './pages/UsersPage'
import FederationPage from './pages/FederationPage'

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<ProtectedRoute />}>
            <Route element={<Layout />}>
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/samples" element={<SamplesPage />} />
              <Route path="/samples/:sampleId/assays/:assayId" element={<SampleDetailPage />} />
              <Route path="/knowledge" element={<KnowledgePage />} />
              <Route path="/lab-dashboard" element={<LabDashboardPage />} />
              <Route path="/gap-analysis" element={<GapAnalysisPage />} />
              <Route path="/cohort" element={<CohortPage />} />
              <Route path="/users" element={<UsersPage />} />
              <Route path="/federation" element={<FederationPage />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
