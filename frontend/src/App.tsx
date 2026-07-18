import { Navigate, Route, Routes } from "react-router-dom";
import AdminApp from "./admin/AdminApp";
import OpApp from "./op/OpApp";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/op" replace />} />
      <Route path="/op/*" element={<OpApp />} />
      <Route path="/admin/*" element={<AdminApp />} />
    </Routes>
  );
}
