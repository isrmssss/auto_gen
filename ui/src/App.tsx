import { NavLink, Route, Routes } from "react-router-dom";
import { ProvidersPage } from "./pages/Providers";
import { ProjectsPage } from "./pages/Projects";
import { ProjectPage } from "./pages/Project";
import { PluginsPage } from "./pages/Plugins";

export function App() {
  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">OpenRD</div>
        <nav className="nav">
          <NavLink to="/" end>
            Projects
          </NavLink>
          <NavLink to="/providers">Providers</NavLink>
          <NavLink to="/plugins">Plugins</NavLink>
        </nav>
        <p className="muted" style={{ fontSize: "0.75rem", marginTop: "auto" }}>
          Local R&amp;D agent. You pay the model API only.
        </p>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/providers" element={<ProvidersPage />} />
          <Route path="/plugins" element={<PluginsPage />} />
          <Route path="/projects/:id" element={<ProjectPage />} />
        </Routes>
      </main>
    </div>
  );
}
