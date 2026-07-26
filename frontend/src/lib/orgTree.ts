// Shared org-hierarchy tree model + helpers for the classic org-chart view (OrgChart).

import type { RepOut } from './types'

export interface TreeNode {
  id: number
  name: string
  designation: string
  rep?: RepOut
  children: TreeNode[]
}

export const DES_COLOR: Record<string, string> = {
  Company: '#3B2596',
  RSM: '#4A2FB0',
  ASM: '#6D4AE0',
  DeputyASM: '#8B6FE8',
  TSO: '#A48BEE',
  PSR: '#B9A6F0',
  DSR: '#CDBFF2',
}
const DES_LABEL: Record<string, string> = { DeputyASM: 'Dy. ASM', Company: 'Colgate' }
export const RANK = ['RSM', 'ASM', 'DeputyASM', 'TSO', 'PSR', 'DSR']

export function desColor(d: string): string {
  return DES_COLOR[d] ?? '#B7A6EE'
}
export function desLabel(d: string): string {
  return DES_LABEL[d] ?? d
}
export function rank(d: string): number {
  const i = RANK.indexOf(d)
  return i === -1 ? RANK.length : i
}

/** Build a single tree rooted at a synthetic company node from a flat rep list. */
export function buildTree(reps: RepOut[]): TreeNode {
  const byId = new Map<number, TreeNode>()
  for (const r of reps)
    byId.set(r.id, { id: r.id, name: r.name, designation: r.designation, rep: r, children: [] })
  const roots: TreeNode[] = []
  for (const r of reps) {
    const node = byId.get(r.id)!
    const mgr = r.reporting_manager_id != null ? byId.get(r.reporting_manager_id) : undefined
    if (mgr) mgr.children.push(node)
    else roots.push(node)
  }
  const root: TreeNode = { id: 0, name: 'Colgate', designation: 'Company', children: roots }
  const sortRec = (n: TreeNode) => {
    n.children.sort(
      (a, b) => rank(a.designation) - rank(b.designation) || a.name.localeCompare(b.name),
    )
    n.children.forEach(sortRec)
  }
  sortRec(root)
  return root
}

/** Collapse penultimate nodes (e.g. TSO → DSRs) so leaf-heavy levels stay legible. */
export function defaultCollapsed(root: TreeNode): Set<number> {
  const s = new Set<number>()
  const walk = (n: TreeNode) => {
    if (n.id !== 0 && n.children.length > 0 && n.children.every((c) => c.children.length === 0))
      s.add(n.id)
    n.children.forEach(walk)
  }
  walk(root)
  return s
}

/** Distinct designations present, in hierarchy order (for the legend). */
export function designationsIn(root: TreeNode): string[] {
  const present = new Set<string>()
  const walk = (n: TreeNode) => {
    present.add(n.designation)
    n.children.forEach(walk)
  }
  walk(root)
  return ['Company', ...RANK].filter((d) => present.has(d))
}
