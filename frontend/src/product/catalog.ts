import { RESOURCE_FIXTURES } from './fixtures'
import type {
  ResourceAttributeValue,
  ResourceDetail,
  ResourceKind,
  ResourcePage,
  ResourceQuery,
} from './types'

const DEFAULT_PAGE_SIZE = 12
const MAX_PAGE_SIZE = 50

function cloneAttribute(value: ResourceAttributeValue): ResourceAttributeValue {
  return Array.isArray(value) ? [...value] : value
}

function cloneResource(resource: ResourceDetail): ResourceDetail {
  return {
    ...resource,
    tags: [...resource.tags],
    attributes: Object.fromEntries(
      Object.entries(resource.attributes).map(([key, value]) => [key, cloneAttribute(value)]),
    ),
  }
}

function normalized(value: string | number | boolean): string {
  return String(value).trim().toLocaleLowerCase('zh-CN')
}

function attributeValues(value: ResourceAttributeValue | undefined): string[] {
  if (value === undefined) return []
  return Array.isArray(value) ? value.map(normalized) : [normalized(value)]
}

function filterValues(resource: ResourceDetail, key: string): string[] {
  if (key === 'availability') return [normalized(resource.availability)]
  if (key === 'source') return [normalized(resource.source)]
  if (key === 'tags') return resource.tags.map(normalized)
  return attributeValues(resource.attributes[key])
}

function matchesFilters(resource: ResourceDetail, filters: ResourceQuery['filters']): boolean {
  if (!filters) return true
  return Object.entries(filters).every(([key, rawExpected]) => {
    const expected = (Array.isArray(rawExpected) ? rawExpected : [rawExpected])
      .map(normalized)
      .filter(Boolean)
    if (!expected.length) return true
    const actual = filterValues(resource, key)
    return expected.some((candidate) => actual.includes(candidate))
  })
}

function matchesSearch(resource: ResourceDetail, rawSearch: string | undefined): boolean {
  const search = rawSearch?.trim().toLocaleLowerCase('zh-CN')
  if (!search) return true
  const searchable = [
    resource.title,
    resource.summary ?? '',
    resource.source,
    ...resource.tags,
    ...Object.values(resource.attributes).flatMap((value) => (
      Array.isArray(value) ? value.map(String) : [String(value)]
    )),
  ].join('\n').toLocaleLowerCase('zh-CN')
  return searchable.includes(search)
}

function encodeCursor(kind: ResourceKind, offset: number): string {
  return `catalog:${kind}:${offset}`
}

function decodeCursor(kind: ResourceKind, cursor: string | null | undefined): number {
  if (!cursor) return 0
  const match = /^catalog:(literature|policy|dataset|method):(\d+)$/.exec(cursor)
  if (!match || match[1] !== kind) return 0
  const offset = Number(match[2])
  return Number.isSafeInteger(offset) && offset >= 0 ? offset : 0
}

export function queryResources(query: ResourceQuery): ResourcePage {
  const pageSize = Math.min(MAX_PAGE_SIZE, Math.max(1, Math.trunc(query.pageSize ?? DEFAULT_PAGE_SIZE)))
  const matching = RESOURCE_FIXTURES[query.kind]
    .filter((resource) => matchesSearch(resource, query.search))
    .filter((resource) => matchesFilters(resource, query.filters))
  const offset = Math.min(decodeCursor(query.kind, query.cursor), matching.length)
  const items = matching.slice(offset, offset + pageSize).map(cloneResource)
  const nextOffset = offset + items.length
  const hasMore = nextOffset < matching.length
  return {
    items,
    total: matching.length,
    nextCursor: hasMore ? encodeCursor(query.kind, nextOffset) : null,
    hasMore,
  }
}

export function getResource(kind: ResourceKind, id: string): ResourceDetail | null {
  const resource = RESOURCE_FIXTURES[kind].find((candidate) => candidate.id === id)
  return resource ? cloneResource(resource) : null
}

export function listResourceFilterValues(kind: ResourceKind, key: string): string[] {
  return [...new Set(RESOURCE_FIXTURES[kind].flatMap((resource) => filterValues(resource, key)))]
    .sort((left, right) => left.localeCompare(right, 'zh-CN'))
}
