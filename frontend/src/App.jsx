import { Navigate, Route, Routes } from "react-router-dom";

import Assistant from "./components/Assistant";
import DemoBanner from "./components/DemoBanner";
import Navbar from "./components/Navbar";
import ProtectedRoute from "./components/ProtectedRoute";
import { useAuth } from "./context/AuthContext";
import AdminDashboard from "./pages/AdminDashboard";
import BookVisit from "./pages/BookVisit";
import BranchQueue from "./pages/BranchQueue";
import CustomerDashboard from "./pages/CustomerDashboard";
import Help from "./pages/Help";
import LoanCalculator from "./pages/LoanCalculator";
import Login from "./pages/Login";

const HOME = { customer: CustomerDashboard, staff: BranchQueue, admin: AdminDashboard };

function Home() {
  const { user } = useAuth();
  const Page = HOME[user.role];
  return <Page />;
}

function CustomerOnly({ children }) {
  return <ProtectedRoute roles={["customer"]}>{children}</ProtectedRoute>;
}

export default function App() {
  return (
    <>
      <DemoBanner />
      <Navbar />
      <main>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Home />
              </ProtectedRoute>
            }
          />
          <Route
            path="/estimate"
            element={
              <CustomerOnly>
                <LoanCalculator />
              </CustomerOnly>
            }
          />
          <Route
            path="/book"
            element={
              <CustomerOnly>
                <BookVisit />
              </CustomerOnly>
            }
          />
          <Route
            path="/help"
            element={
              <CustomerOnly>
                <Help />
              </CustomerOnly>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <Assistant />
    </>
  );
}
