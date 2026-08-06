import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { MotionConfig } from 'framer-motion';
import Dashboard from './pages/Dashboard';
import Rules from './pages/Rules';
import Teach from './pages/Teach';
import Attention from './pages/Attention';
import FollowUps from './pages/FollowUps';
import People from './pages/People';
import Activity from './pages/Activity';
import Mail from './pages/Mail';
import MailThread from './pages/MailThread';
import Accounts from './pages/Accounts';
import AccountDetail from './pages/AccountDetail';
import FolderDetail from './pages/FolderDetail';
import CategoryList from './pages/CategoryList';
import WidgetPage from './pages/WidgetPage';
import Layout from './components/Layout';
import { ToastProvider } from './components/Toast';
import { ErrorBoundary } from './components/ErrorBoundary';
import { useClarittyTheme } from './hooks/useClarittyTheme';

function App() {
  // Theme is inherited from the host (URL param + postMessage), falling back to
  // the OS preference when running standalone. No in-app toggle.
  useClarittyTheme();

  // ToastProvider wraps EVERYTHING (incl. the /widget route) so any component —
  // page or widget — can `useToast()` to surface errors. Never swallow a failed
  // action; catch it, run toApiError(), and show() it. See CLAUDE.md.
  //
  // ErrorBoundary sits OUTSIDE the router, because React unmounts the entire
  // tree on an uncaught render error — one undefined value in one component
  // blanked the deployed app completely, which is the worst thing a user can be
  // shown: indistinguishable from the app being broken, the network being down,
  // or something they did, and offering no way forward.
  return (
    <MotionConfig reducedMotion="user">
    <ToastProvider>
      <ErrorBoundary>
      <Router>
        <Routes>
          {/* Widget route — standalone, no layout (Apple-style widget display). */}
          <Route path="/widget" element={<WidgetPage />} />

          {/* App routes — with the navigation layout. */}
          <Route path="/" element={<Layout><Dashboard /></Layout>} />
          <Route path="/teach" element={<Layout><Teach /></Layout>} />
          <Route path="/followups" element={<Layout><FollowUps /></Layout>} />
          <Route path="/people" element={<Layout><People /></Layout>} />
          <Route path="/attention" element={<Layout><Attention /></Layout>} />
          {/* The book of business — the mailbox grouped into the companies
              behind it, which is the question an owner actually has. */}
          <Route path="/accounts" element={<Layout><Accounts /></Layout>} />
          <Route path="/accounts/:accountKey" element={<Layout><AccountDetail /></Layout>} />
          {/* The client half — read a whole thread, reply in context, write to
              someone the app never flagged. Keeps its routes after losing its
              nav slot: every account row links into it. */}
          <Route path="/mail" element={<Layout><Mail /></Layout>} />
          <Route path="/mail/:threadId" element={<Layout><MailThread /></Layout>} />
          {/* What the app did while nobody was looking — activity, folders, insights. */}
          <Route path="/activity" element={<Layout><Activity /></Layout>} />
          <Route path="/folders/:folderId" element={<Layout><FolderDetail /></Layout>} />
          <Route path="/cleanup/:category" element={<Layout><CategoryList /></Layout>} />
          <Route path="/rules" element={<Layout><Rules /></Layout>} />
        </Routes>
      </Router>
      </ErrorBoundary>
    </ToastProvider>
    </MotionConfig>
  );
}

export default App;
