import { FaPlus, FaMinus } from 'react-icons/fa6'
import { desColor, desLabel, type TreeNode } from '../lib/orgTree'

function NodeBox({
  node,
  collapsed,
  onToggle,
}: {
  node: TreeNode
  collapsed: boolean
  onToggle: (id: number) => void
}) {
  const isCore = node.id === 0
  const hasChildren = node.children.length > 0
  const color = desColor(node.designation)
  return (
    <div
      className="relative inline-flex min-w-[132px] max-w-[190px] flex-col items-center gap-1 rounded-tile border border-line bg-white px-3 pb-3 pt-2.5 shadow-soft-sm"
      style={{ borderTop: `3px solid ${color}` }}
    >
      <span
        className="rounded-chip px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white"
        style={{ background: color }}
      >
        {desLabel(node.designation)}
      </span>
      <span className="text-center text-sm font-semibold leading-tight text-ink">{node.name}</span>
      {node.rep?.employee_code && (
        <span className="text-[10px] text-muted">{node.rep.employee_code}</span>
      )}
      {node.rep && (node.rep.territory_name || node.rep.area_name || node.rep.region_name) && (
        <span className="text-center text-[10px] leading-tight text-muted">
          {node.rep.territory_name || node.rep.area_name || node.rep.region_name}
        </span>
      )}
      {hasChildren && !isCore && (
        <button
          type="button"
          onClick={() => onToggle(node.id)}
          className="absolute -bottom-3 left-1/2 z-10 flex h-6 min-w-6 -translate-x-1/2 items-center justify-center gap-0.5 rounded-full border border-line bg-white px-1.5 text-[10px] font-bold text-violet shadow-soft-sm transition-colors hover:bg-tint"
          aria-label={collapsed ? 'Expand reports' : 'Collapse reports'}
        >
          {collapsed ? (
            <>
              <FaPlus className="h-2 w-2" />
              {node.children.length}
            </>
          ) : (
            <FaMinus className="h-2 w-2" />
          )}
        </button>
      )}
    </div>
  )
}

function TreeLi({
  node,
  collapsed,
  onToggle,
}: {
  node: TreeNode
  collapsed: Set<number>
  onToggle: (id: number) => void
}) {
  const isCollapsed = collapsed.has(node.id)
  const showChildren = node.children.length > 0 && !isCollapsed
  return (
    <li>
      <NodeBox node={node} collapsed={isCollapsed} onToggle={onToggle} />
      {showChildren && (
        <ul>
          {node.children.map((c) => (
            <TreeLi key={c.id} node={c} collapsed={collapsed} onToggle={onToggle} />
          ))}
        </ul>
      )}
    </li>
  )
}

export default function OrgChart({
  root,
  collapsed,
  onToggle,
}: {
  root: TreeNode
  collapsed: Set<number>
  onToggle: (id: number) => void
}) {
  return (
    <div className="bb-orgtree overflow-x-auto pb-4">
      <ul>
        <TreeLi node={root} collapsed={collapsed} onToggle={onToggle} />
      </ul>
    </div>
  )
}
