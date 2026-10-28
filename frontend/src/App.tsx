import { NavLink, Navigate, Route, Routes } from "react-router-dom";

import { GlobalSearch } from "./components/GlobalSearch";
import { initials, roleLabel } from "./lib/friendly";
import { useMe } from "./lib/useMe";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { CasePage } from "./pages/CasePage";
import { InvestigationPage } from "./pages/InvestigationPage";
import { ResolutionPage } from "./pages/ResolutionPage";
import { RulesPage } from "./pages/RulesPage";
import { Icon, type IconName } from "./ui/Icon";
import { useTheme } from "./ui/theme";

const NAV: { to: string; label: string; icon: IconName }[] = [
  { to: "/investigate", label: "Investigate", icon: "network" },
  { to: "/analytics", label: "Analytics", icon: "analytics" },
  { to: "/resolution", label: "Resolution", icon: "resolution" },
  { to: "/rules", label: "Rules", icon: "rules" },
];

const THEME: Record<string, { icon: IconName; next: string }> = {
  system: { icon: "monitor", next: "light" },
  light: { icon: "sun", next: "dark" },
  dark: { icon: "moon", next: "system" },
};

export function App() {
  const [theme, cycleTheme] = useTheme();
  const { me } = useMe();

  return (
    <div className="shell">
      <header className="topbar">
        <NavLink to="/investigate" className="brand" aria-label="Graphy home">
          <span className="logo">
            <Icon name="network" size={18} />
          </span>
          <span className="brand-name">Graphy</span>
        </NavLink>
        <nav aria-label="Main">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to}>
              <Icon name={n.icon} size={16} />
              <span>{n.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="topbar-end">
          <GlobalSearch />
          <button
            type="button"
            className="icon-btn"
            onClick={cycleTheme}
            title={`Theme: ${theme}. Click for ${THEME[theme].next}.`}
            aria-label={`Theme: ${theme}. Switch to ${THEME[theme].next}.`}
          >
            <Icon name={THEME[theme].icon} />
          </button>
          {me && (
            <span
              className="avatar"
              title={`${me.subject}\nRoles: ${me.roles.map(roleLabel).join(", ")}`}
              aria-label={`Signed in as ${me.subject}`}
            >
              {initials(me.subject)}
            </span>
          )}
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/investigate" element={<InvestigationPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/analytics/:caseKey" element={<CasePage />} />
          <Route path="/resolution" element={<ResolutionPage />} />
          <Route path="/rules" element={<RulesPage />} />
          <Route path="*" element={<Navigate to="/investigate" replace />} />
        </Routes>
      </main>
    </div>
  );
}
