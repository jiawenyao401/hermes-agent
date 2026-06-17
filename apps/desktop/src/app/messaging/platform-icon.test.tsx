import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PlatformAvatar } from './platform-icon'

describe('PlatformAvatar', () => {
  it.each([
    ['feishu', '飞书', 'feishu.png'],
    ['dingtalk', '钉钉', 'dingtalk.png'],
    ['wecom', '企业微信', 'wecom.png'],
    ['wecom_callback', '企业微信', 'wecom.png']
  ])('renders the local platform icon for %s', (platformId, platformName, filename) => {
    const { container } = render(<PlatformAvatar platformId={platformId} platformName={platformName} />)

    const image = container.querySelector('img')

    expect(image?.getAttribute('src')).toContain(`/messaging-icons/${filename}`)
  })
})
