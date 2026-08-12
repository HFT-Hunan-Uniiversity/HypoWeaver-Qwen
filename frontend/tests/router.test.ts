import { describe, expect, it } from 'vitest'
import { hashOf, viewFromHash } from '../src/runtime/router'

describe('frontend hash router', () => {
  it('redirects legacy studio to projects', () => {
    expect(viewFromHash('#studio')).toEqual({ kind: 'projects' })
  })

  it('parses project discovery routes and defaults invalid steps', () => {
    expect(viewFromHash('#project/demo/discovery/ideas')).toEqual({
      kind: 'discovery',
      id: 'demo',
      step: 'ideas',
    })
    expect(viewFromHash('#project/demo/discovery/unknown')).toEqual({
      kind: 'discovery',
      id: 'demo',
      step: 'brief',
    })
  })

  it('parses library routes and defaults to literature', () => {
    expect(viewFromHash('#library/dataset')).toEqual({ kind: 'library', resourceKind: 'dataset' })
    expect(viewFromHash('#library/unknown')).toEqual({ kind: 'library', resourceKind: 'literature' })
  })

  it('round-trips encoded project and task identifiers', () => {
    const project = { kind: 'project', id: '研究 01', section: 'overview' } as const
    const task = { kind: 'task', id: 'mock/01' } as const
    expect(viewFromHash(hashOf(project))).toEqual(project)
    expect(viewFromHash(hashOf(task))).toEqual(task)
  })
})
