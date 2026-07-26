import { useQuery } from '@tanstack/react-query'
import { FaStore, FaMapLocationDot, FaBullseye, FaPhoneVolume } from 'react-icons/fa6'
import { Bar } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
  type TooltipItem,
} from 'chart.js'
import PageHeader from '../components/PageHeader'
import { ErrorCard, LoadingCard } from '../components/States'
import { api, rupees } from '../lib/api'
import { statusChip } from '../lib/ui'
import type { Overview as OverviewData } from '../lib/types'

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend)

const CHART_PRIMARY = '#6D4AE0'
const CHART_MUTED = '#CDBFF2'

function Kpi({
  kicker,
  value,
  sub,
  icon: Icon,
  grad,
}: {
  kicker: string
  value: string
  sub?: string
  icon: React.ComponentType<{ className?: string }>
  grad: string
}) {
  return (
    <div className="bb-card">
      <div className="bb-feature">
        <div className={`bb-tile ${grad}`}>
          <Icon className="h-[44%] w-[44%]" />
        </div>
        <div className="min-w-0">
          <div className="bb-kicker">{kicker}</div>
          <div className="bb-stat">{value}</div>
          {sub && <div className="mt-1 truncate text-xs text-muted">{sub}</div>}
        </div>
      </div>
    </div>
  )
}

export default function Overview() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['overview'],
    queryFn: () => api<OverviewData>('/api/overview'),
  })

  return (
    <>
      <PageHeader
        kicker="Overview"
        title="Distribution at a glance"
        subtitle={
          data
            ? `${data.company} · coverage, secondary-sales achievement, active outlets and today's calls.`
            : "Coverage, secondary-sales achievement, active outlets and today's calls."
        }
      />

      {isLoading && <LoadingCard label="Loading overview…" />}
      {isError && <ErrorCard error={error} />}

      {data && (
        <>
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-4">
            <Kpi
              kicker="Active outlets"
              value={data.active_outlets.toLocaleString('en-IN')}
              sub={`of ${data.total_outlets.toLocaleString('en-IN')} total`}
              icon={FaStore}
              grad="bg-grad-violet"
            />
            <Kpi
              kicker="Coverage"
              value={`${data.coverage_pct.toFixed(1)}%`}
              sub="outlets billed this cycle"
              icon={FaMapLocationDot}
              grad="bg-grad-periwinkle"
            />
            <Kpi
              kicker="Secondary achievement"
              value={`${data.secondary_achievement_pct.toFixed(1)}%`}
              sub={`${data.orders_total.toLocaleString('en-IN')} orders`}
              icon={FaBullseye}
              grad="bg-grad-indigo"
            />
            <Kpi
              kicker="Calls today"
              value={data.calls_today.toLocaleString('en-IN')}
              sub="voice-agent calls"
              icon={FaPhoneVolume}
              grad="bg-grad-lavender"
            />
          </div>

          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
            <div className="bb-card lg:col-span-2">
              <div className="bb-kicker mb-1">Region achievement</div>
              <h3 className="bb-h3 mb-4">Target vs. achieved</h3>
              {data.region_achievement.length === 0 ? (
                <p className="text-sm text-muted">No region data.</p>
              ) : (
                <div className="h-[340px]">
                  <Bar
                    data={{
                      labels: data.region_achievement.map((r) => r.name),
                      datasets: [
                        {
                          label: 'Target',
                          data: data.region_achievement.map((r) => r.target_paise / 100),
                          backgroundColor: CHART_MUTED,
                          borderRadius: 6,
                        },
                        {
                          label: 'Achieved',
                          data: data.region_achievement.map((r) => r.achieved_paise / 100),
                          backgroundColor: CHART_PRIMARY,
                          borderRadius: 6,
                        },
                      ],
                    }}
                    options={{
                      responsive: true,
                      maintainAspectRatio: false,
                      plugins: {
                        legend: {
                          position: 'top',
                          align: 'end',
                          labels: { boxWidth: 12, usePointStyle: true, color: '#6F6A82' },
                        },
                        tooltip: {
                          callbacks: {
                            label: (item: TooltipItem<'bar'>) =>
                              `${item.dataset.label}: ${rupees((item.parsed.y ?? 0) * 100)}`,
                          },
                        },
                      },
                      scales: {
                        x: { grid: { display: false }, ticks: { color: '#6F6A82' } },
                        y: {
                          grid: { color: '#ECE7F8' },
                          ticks: {
                            color: '#6F6A82',
                            callback: (v) => rupees(Number(v) * 100),
                          },
                        },
                      },
                    }}
                  />
                </div>
              )}
            </div>

            <div className="bb-card">
              <div className="bb-kicker mb-1">Recent orders</div>
              <h3 className="bb-h3 mb-4">Latest activity</h3>
              {data.recent_orders.length === 0 ? (
                <p className="text-sm text-muted">No recent orders.</p>
              ) : (
                <ul className="divide-y divide-line">
                  {data.recent_orders.map((o) => (
                    <li key={o.id} className="flex items-center justify-between gap-3 py-3">
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold text-ink">
                          {o.outlet_name}
                        </div>
                        <div className="text-xs text-muted">
                          {o.n_items} item{o.n_items === 1 ? '' : 's'}
                        </div>
                      </div>
                      <div className="flex shrink-0 flex-col items-end gap-1">
                        <span className="font-sans text-sm font-semibold text-violet">
                          {rupees(o.total_paise)}
                        </span>
                        <span className={`bb-chip ${statusChip(o.status)}`}>{o.status}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </>
      )}
    </>
  )
}
