import { Navigate, Route, Routes } from "react-router-dom";
import AdminHome from "./admin/AdminHome";
import OpApp from "./op/OpApp";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/op" replace />} />
      <Route path="/op/*" element={<OpApp />} />
      <Route path="/admin" element={<AdminHome />} />
    </Routes>
  );
}
