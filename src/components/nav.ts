import { BarChart3, Camera, CircleUserRound, Home } from 'lucide-react'
import type { AppTab } from '../types/domain'

export const tabPaths: Record<AppTab, string> = {
  home: '/',
  analyze: '/analyze',
  progress: '/progress',
  profile: '/me',
}

export const navItems: Array<{ id: AppTab; label: string; icon: typeof Home }> = [
  { id: 'home', label: '首页', icon: Home },
  { id: 'analyze', label: '分析', icon: Camera },
  { id: 'progress', label: '进步', icon: BarChart3 },
  { id: 'profile', label: '我的', icon: CircleUserRound },
]
