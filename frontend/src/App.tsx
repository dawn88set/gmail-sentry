import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Tasks from './pages/Tasks';
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
    <ToastProvider>
      <Router>
        <Routes>
          {/* Widget route — standalone, no layout (Apple-style widget display). */}
          <Route path="/widget" element={<WidgetPage />} />

          {/* App routes — with the navigation layout. */}
          <Route path="/" element={<Layout><Dashboard /></Layout>} />
          <Route path="/tasks" element={<Layout><Tasks /></Layout>} />
        </Routes>
      </Router>
    </ToastProvider>
  );
}

export default App;
