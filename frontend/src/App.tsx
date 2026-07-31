import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { MotionConfig } from 'framer-motion';
import Dashboard from './pages/Dashboard';
import Rules from './pages/Rules';
import Teach from './pages/Teach';
import Attention from './pages/Attention';
import FollowUps from './pages/FollowUps';
import CategoryList from './pages/CategoryList';
import WidgetPage from './pages/WidgetPage';
import Layout from './components/Layout';
import { ToastProvider } from './components/Toast';
import { useClarittyTheme } from './hooks/useClarittyTheme';

function App() {
  // Theme is inherited from the host (URL param + postMessage), falling back to
  // the OS preference when running standalone. No in-app toggle.
  useClarittyTheme();

  // ToastProvider wraps EVERYTHING (incl. the /widget route) so any component —
  // page or widget — can `useToast()` to surface errors. Never swallow a failed
  // action; catch it, run toApiError(), and show() it. See CLAUDE.md.
  return (
    <MotionConfig reducedMotion="user">
    <ToastProvider>
      <Router>
        <Routes>
          {/* Widget route — standalone, no layout (Apple-style widget display). */}
          <Route path="/widget" element={<WidgetPage />} />

          {/* App routes — with the navigation layout. */}
          <Route path="/" element={<Layout><Dashboard /></Layout>} />
          <Route path="/teach" element={<Layout><Teach /></Layout>} />
          <Route path="/followups" element={<Layout><FollowUps /></Layout>} />
          <Route path="/attention" element={<Layout><Attention /></Layout>} />
          <Route path="/cleanup/:category" element={<Layout><CategoryList /></Layout>} />
          <Route path="/rules" element={<Layout><Rules /></Layout>} />
        </Routes>
      </Router>
    </ToastProvider>
    </MotionConfig>
  );
}

export default App;
