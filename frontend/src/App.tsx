import { Navigate, Route, Routes } from "react-router-dom";
import AdminHome from "./admin/AdminHome";
import OpHome from "./op/OpHome";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/op" replace />} />
      <Route path="/op" element={<OpHome />} />
      <Route path="/admin" element={<AdminHome />} />
    </Routes>
  );
}
