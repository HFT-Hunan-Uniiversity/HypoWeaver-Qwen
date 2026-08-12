import { getResource, queryResources } from './catalog'
import {
  createMockTask,
  decideMockGate,
  deleteMockTask,
  getMockTask,
  isMockTaskId,
  listMockTasks,
  subscribeMockTask,
  subscribeMockTasks,
} from '../data/mockPipeline'
import {
  addProjectResource,
  buildDiscoveryHandoff,
  createProject,
  getEvidenceBundle,
  getProject,
  getSelectedProjectId,
  listProjects,
  removeProjectResource,
  selectDiscoveryIdea,
  setSelectedProjectId,
  subscribeProductStore,
  updateDiscoveryDraft,
  updateDiscoveryStep,
  updateProject,
} from './store'
import type { FrontendDataSource } from './types'

// Contract placeholder only. The fixture source below never issues a network request.
export const FUTURE_CATALOG_API_BASE = '/api/v1/catalog' as const

export const frontendDataSource: FrontendDataSource = {
  listProjects,
  getProject,
  createProject,
  updateProject,
  getSelectedProjectId,
  setSelectedProjectId,
  updateDiscoveryDraft,
  updateDiscoveryStep,
  selectDiscoveryIdea,
  queryResources,
  getResource,
  addProjectResource,
  removeProjectResource,
  getEvidenceBundle,
  buildDiscoveryHandoff,
  listDemoTasks: listMockTasks,
  getDemoTask: getMockTask,
  isDemoTaskId: isMockTaskId,
  createDemoTask: createMockTask,
  deleteDemoTask: deleteMockTask,
  decideDemoGate: decideMockGate,
  subscribeDemoTask: subscribeMockTask,
  subscribeDemoTasks: subscribeMockTasks,
  subscribe: subscribeProductStore,
}
