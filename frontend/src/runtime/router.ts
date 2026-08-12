export type LibraryKind = 'literature' | 'policy' | 'dataset' | 'method'

export type DiscoveryStep =
  | 'brief'
  | 'resources'
  | 'gaps'
  | 'ideas'
  | 'decision'
  | 'handoff'

export type ShellView =
  | { kind: 'new' }
  | { kind: 'projects' }
  | { kind: 'project'; id: string; section: 'overview' }
  | { kind: 'discovery'; id: string; step: DiscoveryStep }
  | { kind: 'library'; resourceKind: LibraryKind }
  | { kind: 'settings' }
  | { kind: 'task'; id: string }

const LIBRARY_KINDS = new Set<LibraryKind>(['literature', 'policy', 'dataset', 'method'])
const DISCOVERY_STEPS = new Set<DiscoveryStep>(['brief', 'resources', 'gaps', 'ideas', 'decision', 'handoff'])

function decodeSegment(value: string): string {
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

export function viewFromHash(hash = window.location.hash): ShellView {
  const value = hash.replace(/^#/, '')
  const segments = value.split('/').filter(Boolean)

  if (segments[0] === 'task' && segments[1]) {
    return { kind: 'task', id: decodeSegment(segments[1]) }
  }

  if (segments[0] === 'project' && segments[1]) {
    const id = decodeSegment(segments[1])
    if (segments[2] === 'discovery') {
      const requested = segments[3] as DiscoveryStep | undefined
      return {
        kind: 'discovery',
        id,
        step: requested && DISCOVERY_STEPS.has(requested) ? requested : 'brief',
      }
    }
    return { kind: 'project', id, section: 'overview' }
  }

  if (segments[0] === 'library') {
    const requested = segments[1] as LibraryKind | undefined
    return {
      kind: 'library',
      resourceKind: requested && LIBRARY_KINDS.has(requested) ? requested : 'literature',
    }
  }

  if (value === 'projects' || value === 'studio') return { kind: 'projects' }
  if (value === 'settings') return { kind: 'settings' }
  if (value === 'runs') return { kind: 'new' }
  return { kind: 'new' }
}

export function hashOf(view: ShellView): string {
  switch (view.kind) {
    case 'task':
      return `#task/${encodeURIComponent(view.id)}`
    case 'project':
      return `#project/${encodeURIComponent(view.id)}/overview`
    case 'discovery':
      return `#project/${encodeURIComponent(view.id)}/discovery/${view.step}`
    case 'library':
      return `#library/${view.resourceKind}`
    default:
      return `#${view.kind}`
  }
}

export function isProjectView(
  view: ShellView,
): view is Extract<ShellView, { kind: 'project' | 'discovery' }> {
  return view.kind === 'project' || view.kind === 'discovery'
}
