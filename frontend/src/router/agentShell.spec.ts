import { describe, expect, it } from 'vitest'

import { agentCounterpart } from './guards'
import { AGENT_MENU_EXTRA, AGENT_TABS, INVESTOR_TABS } from './tabs'

describe('the integrator stays in the integrator shell', () => {
  it('maps a buyer-shell route to the integrator one', () => {
    expect(agentCounterpart('investor-deposit')).toBe('agent-deposit')
    expect(agentCounterpart('investor-balance')).toBe('agent-balance')
    expect(agentCounterpart('investor-settings')).toBe('agent-settings')
    expect(agentCounterpart('investor-company-position')).toBe('agent-company-position')
  })

  it('leaves other routes alone', () => {
    expect(agentCounterpart('agent-deposit')).toBeNull()
    expect(agentCounterpart('investor-more')).toBeNull()
    expect(agentCounterpart('login')).toBeNull()
    expect(agentCounterpart(undefined)).toBeNull()
  })
})

describe('the integrator tabs', () => {
  it('are five, in the buyer order, with no More tab', () => {
    expect(AGENT_TABS.map((t) => t.id)).toEqual([
      'home',
      'market',
      'portfolio',
      'partners',
      'settings',
    ])
    expect(AGENT_TABS.map((t) => t.id)).not.toContain('more')
    expect(AGENT_TABS[0]?.id).toBe(INVESTOR_TABS[0]?.id)
    expect(AGENT_TABS[4]?.id).toBe(INVESTOR_TABS[4]?.id)
  })

  it('keep every inner section one line each in the web menu', () => {
    const paths = AGENT_MENU_EXTRA.map((t) => t.path)
    expect(paths).toContain('/agent/news')
    expect(paths).toContain('/agent/partners/balance')
    expect(paths).toContain('/agent/docs')
    expect(new Set(paths).size).toBe(paths.length)
  })
})
