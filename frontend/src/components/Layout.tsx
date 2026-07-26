import type { ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import {
  FaChartLine,
  FaMapLocationDot,
  FaStore,
  FaSitemap,
  FaPhoneVolume,
  FaListCheck,
} from 'react-icons/fa6'

const NAV = [
  { to: '/', label: 'Overview', icon: FaChartLine, end: true },
  { to: '/agent', label: 'Voice Agents', icon: FaPhoneVolume, end: false },
  { to: '/field-ops', label: 'Field Ops', icon: FaListCheck, end: false },
  { to: '/regions', label: 'Region Targets', icon: FaMapLocationDot, end: false },
  { to: '/retailers', label: 'Retailers', icon: FaStore, end: false },
  { to: '/org', label: 'Stockists', icon: FaSitemap, end: false },
]

function Soundwave() {
  return (
    <svg viewBox="-100 -100 200 200" className="h-1/2 w-1/2" aria-hidden>
      <g stroke="#fff" strokeWidth="8" fill="none" opacity="0.9">
        <circle r="18" />
        <circle r="44" />
        <circle r="72" />
      </g>
    </svg>
  )
}

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-64 shrink-0 flex-col border-r border-line bg-white/70 px-4 py-6 backdrop-blur">
        <div className="mb-8 px-2">
          <div className="flex items-center gap-3">
            <div className="bb-tile h-11 w-11 bg-grad-violet">
              <Soundwave />
            </div>
            <div>
              <div className="font-display text-lg font-bold leading-none text-ink">BharatBeat</div>
              <div className="text-[11px] text-muted">Voice AI · Rural FMCG</div>
            </div>
          </div>
        </div>
        <nav className="space-y-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => `bb-navlink ${isActive ? 'bb-navlink-active' : ''}`}
            >
              <Icon className="h-4 w-4 text-violet" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto px-2 pt-6">
          <span className="bb-chip bg-tint text-violet">Colgate · demo tenant</span>
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-8 py-8">{children}</main>
    </div>
  )
}
