import type { MessagingPlatformInfo } from '@/types/hermes'

const AGENTOS_PLATFORM_ORDER = ['feishu', 'weixin', 'qqbot', 'wecom', 'dingtalk'] as const

const PLATFORM_ALIASES: Record<string, (typeof AGENTOS_PLATFORM_ORDER)[number]> = {
  dingtalk: 'dingtalk',
  feishu: 'feishu',
  qqbot: 'qqbot',
  wecom: 'wecom',
  wecom_callback: 'wecom',
  weixin: 'weixin'
}

const PLATFORM_LABELS: Record<(typeof AGENTOS_PLATFORM_ORDER)[number], string> = {
  dingtalk: 'DingTalk',
  feishu: 'Feishu / Lark',
  qqbot: 'QQ Bot',
  wecom: 'WeCom',
  weixin: 'WeChat'
}

const PLATFORM_ORDER = new Map(AGENTOS_PLATFORM_ORDER.map((id, index) => [id, index]))

function canonicalPlatformId(source: null | string | undefined) {
  const id = source?.trim().toLowerCase()

  return id ? PLATFORM_ALIASES[id] : undefined
}

export function agentOSMessagingPlatformLabel(source: null | string | undefined): string | null {
  const canonical = canonicalPlatformId(source)

  return canonical ? PLATFORM_LABELS[canonical] : null
}

export function agentOSMessagingPlatformGroupId(source: null | string | undefined): string | null {
  return canonicalPlatformId(source) ?? null
}

export function agentOSMessagingPlatformSortValue(source: null | string | undefined): number {
  const canonical = canonicalPlatformId(source)

  return canonical ? (PLATFORM_ORDER.get(canonical) ?? Number.MAX_SAFE_INTEGER) : Number.MAX_SAFE_INTEGER
}

export function isAgentOSMessagingPlatform(source: null | string | undefined): boolean {
  return canonicalPlatformId(source) != null
}

function platformPreference(platform: MessagingPlatformInfo): number {
  if (canonicalPlatformId(platform.id) === 'wecom') {
    return platform.id === 'wecom_callback' ? 0 : 1
  }

  return 0
}

function agentOSPlatformCopy(platform: MessagingPlatformInfo): MessagingPlatformInfo {
  const label = agentOSMessagingPlatformLabel(platform.id)

  return {
    ...platform,
    description: platform.description.replace(/\bHermes Agent\b/g, 'AgentOS').replace(/\bHermes\b/g, 'AgentOS'),
    name: label ?? platform.name
  }
}

export function filterAgentOSMessagingPlatforms(platforms: MessagingPlatformInfo[]): MessagingPlatformInfo[] {
  const selected = new Map<string, MessagingPlatformInfo>()

  for (const platform of platforms) {
    const canonical = canonicalPlatformId(platform.id)

    if (!canonical) {
      continue
    }

    const current = selected.get(canonical)

    if (!current || platformPreference(platform) < platformPreference(current)) {
      selected.set(canonical, platform)
    }
  }

  return [...selected.values()]
    .map(agentOSPlatformCopy)
    .sort((a, b) => agentOSMessagingPlatformSortValue(a.id) - agentOSMessagingPlatformSortValue(b.id))
}
