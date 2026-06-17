import type { ReactNode } from 'react'
import { useEffect, useRef, useState } from 'react'

import type { DesktopEnterpriseAuthStatus } from '@/global'

import { BrandMark } from './brand-mark'
import { PageLoader } from './page-loader'
import { Button } from './ui/button'

interface EnterpriseAuthGateProps {
  children: ReactNode
}

const UNAUTHORIZED_STATE: DesktopEnterpriseAuthStatus = {
  authorized: false,
  authorizedAt: null,
  gatewayUrl: '',
  sessionTokenPreview: null,
  username: null
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '授权流程启动失败，请重试。'
}

export function EnterpriseAuthGate({ children }: EnterpriseAuthGateProps) {
  const [status, setStatus] = useState<DesktopEnterpriseAuthStatus | null>(null)
  const [opening, setOpening] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const autoOpenedRef = useRef(false)

  const openLogin = async () => {
    if (!window.hermesDesktop?.enterpriseAuth) {
      setError('桌面授权桥接不可用。')
      return
    }

    setOpening(true)
    setError(null)
    try {
      await window.hermesDesktop.enterpriseAuth.beginLogin()
    } catch (nextError) {
      setError(errorMessage(nextError))
    } finally {
      setOpening(false)
    }
  }

  useEffect(() => {
    let cancelled = false

    const load = async () => {
      if (!window.hermesDesktop?.enterpriseAuth) {
        if (!cancelled) {
          setError('桌面授权桥接不可用。')
          setStatus(UNAUTHORIZED_STATE)
        }
        return
      }

      try {
        const next = await window.hermesDesktop.enterpriseAuth.getStatus()
        if (!cancelled) {
          setStatus(next)
        }
      } catch (nextError) {
        if (!cancelled) {
          setError(errorMessage(nextError))
          setStatus(UNAUTHORIZED_STATE)
        }
      }
    }

    void load()

    const unsubscribe = window.hermesDesktop?.enterpriseAuth?.onChanged?.(next => {
      setError(null)
      setStatus(next)
    })

    return () => {
      cancelled = true
      unsubscribe?.()
    }
  }, [])

  useEffect(() => {
    if (!status || status.authorized || autoOpenedRef.current) {
      return
    }

    autoOpenedRef.current = true
    void openLogin()
  }, [status])

  if (!status) {
    return <PageLoader className="bg-(--ui-bg-chrome)" label="正在检查授权状态" />
  }

  if (status.authorized) {
    return <>{children}</>
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-(--ui-bg-chrome) text-(--ui-text-primary)">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(0,83,253,0.09),_transparent_44%),linear-gradient(180deg,_rgba(248,251,255,0.96)_0%,_rgba(243,247,255,0.98)_100%)]" />
      <div className="relative flex min-h-screen items-center justify-center px-6 py-10">
        <div className="w-full max-w-[460px] rounded-[28px] border border-white/70 bg-white/92 px-8 py-9 shadow-[0_30px_80px_rgba(24,54,127,0.12)] backdrop-blur">
          <BrandMark className="mx-auto size-18 rounded-2xl shadow-[0_12px_30px_rgba(0,83,253,0.12)]" />
          <div className="mt-6 text-center">
            <h1 className="text-[34px] leading-none font-bold tracking-normal text-[#1452f4]">AgentOS</h1>
            <p className="mt-4 text-[15px] leading-7 text-slate-500">
              首次使用需要先完成企业授权。系统会在浏览器中打开登录页，登录成功后自动返回客户端并接入企业远程网关。
            </p>
          </div>

          {error ? <div className="mt-5 rounded-2xl bg-[#fff1f2] px-4 py-3 text-[14px] text-[#be123c]">{error}</div> : null}

          <div className="mt-7 flex flex-col gap-3">
            <Button
              className="h-12 rounded-full bg-black text-[15px] font-medium text-white hover:bg-black/90"
              disabled={opening}
              onClick={() => void openLogin()}
              type="button"
            >
              {opening ? '正在打开浏览器...' : '打开浏览器去授权'}
            </Button>
            <div className="text-center text-[13px] text-slate-400">浏览器登录成功后会自动回到 AgentOS。</div>
          </div>
        </div>
      </div>
    </div>
  )
}
