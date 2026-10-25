// =============================================================================
// The cabinet's icons: the design system's set (style P1), drawn from the sprite
// =============================================================================
//
// Each export is a component that draws one key of
// design-system/components/icons/icons.json as <svg><use href="#i-key"/></svg>;
// the sprite (src/assets/icons/ds-icons.svg) is put into the document once by
// main.ts. The exports keep the names and the `size` prop of the lucide icons
// they replace, so a screen that passes an icon as a component keeps working.
//
import { defineComponent, h } from 'vue'

// size: 'sm' (16) or 'md' (24, the default), the system's two icon classes, or a
// number of pixels the screens write (`:size="20"`). A number is read as the NEAREST
// STEP of the system's icon scale and drawn from its token, never as pixels:
// 16 is --icon-size-sm (14 and 18 round to it), 20 is --size-2xs, 24 --icon-size-md,
// 32 --icon-size-lg, 40 --size-xl and 48 --icon-size-xl (56, 64 and 72 round to it;
// a larger picture is the empty state's or the hero's own piece).
const STEPS: Array<{ px: number; token?: string; md?: boolean }> = [
  { px: 16 },
  { px: 20, token: '--size-2xs' },
  { px: 24, md: true },
  { px: 32, token: '--icon-size-lg' },
  { px: 40, token: '--size-xl' },
  { px: 48, token: '--icon-size-xl' },
]

function nearestStep(px: number) {
  return STEPS.reduce((best, step) =>
    Math.abs(step.px - px) < Math.abs(best.px - px) ? step : best,
  )
}

export function icon(name: string, key: string) {
  return defineComponent({
    name,
    props: { size: { type: [Number, String], default: 'md' } },
    setup(props) {
      return () => {
        const px = Number(props.size)
        const step = Number.isFinite(px) ? nearestStep(px) : undefined
        const md = props.size === 'md' || step?.md === true
        return h(
          'svg',
          {
            class: ['ds-icon', md && 'ds-icon--md'],
            'aria-hidden': 'true',
            viewBox: '0 0 24 24',
            style: step?.token
              ? { inlineSize: `var(${step.token})`, blockSize: `var(${step.token})` }
              : undefined,
          },
          [h('use', { href: '#i-' + key })],
        )
      }
    },
  })
}

export const AlertTriangle = icon('AlertTriangle', 'alert-triangle')
export const ArrowDownLeft = icon('ArrowDownLeft', 'arrow-down-left')
export const ArrowDownToLine = icon('ArrowDownToLine', 'arrow-down-to-line')
export const ArrowLeft = icon('ArrowLeft', 'arrow-left')
export const ArrowUpFromLine = icon('ArrowUpFromLine', 'arrow-up-from-line')
export const ArrowUpRight = icon('ArrowUpRight', 'arrow-up-right')
export const Ban = icon('Ban', 'ban')
export const Banknote = icon('Banknote', 'banknote')
export const BarChart3 = icon('BarChart3', 'bar-chart')
export const Bell = icon('Bell', 'bell')
export const Briefcase = icon('Briefcase', 'briefcase')
export const Building = icon('Building', 'building')
export const Building2 = icon('Building2', 'building')
export const Calendar = icon('Calendar', 'calendar')
export const CalendarClock = icon('CalendarClock', 'calendar-clock')
export const CalendarDays = icon('CalendarDays', 'calendar-days')
export const Check = icon('Check', 'check')
export const CheckCheck = icon('CheckCheck', 'check-check')
export const ChevronDown = icon('ChevronDown', 'chevron-down')
export const ChevronLeft = icon('ChevronLeft', 'chevron-left')
export const PanelLeftClose = icon('PanelLeftClose', 'panel-left-close')
export const PanelLeftOpen = icon('PanelLeftOpen', 'panel-left-open')
export const ChevronRight = icon('ChevronRight', 'chevron-right')
export const ChevronUp = icon('ChevronUp', 'chevron-up')
export const Clock = icon('Clock', 'clock')
export const Coins = icon('Coins', 'coins')
export const Copy = icon('Copy', 'copy')
export const CreditCard = icon('CreditCard', 'credit-card')
export const Download = icon('Download', 'download')
export const ExternalLink = icon('ExternalLink', 'external-link')
export const Eye = icon('Eye', 'eye')
export const EyeOff = icon('EyeOff', 'eye-off')
export const File = icon('File', 'file')
export const FileArchive = icon('FileArchive', 'file-archive')
export const FileSignature = icon('FileSignature', 'file-signature')
export const FileSpreadsheet = icon('FileSpreadsheet', 'file-spreadsheet')
export const FileText = icon('FileText', 'file-text')
export const Gauge = icon('Gauge', 'gauge')
export const Ghost = icon('Ghost', 'ghost')
export const Gift = icon('Gift', 'gift')
export const Globe = icon('Globe', 'globe')
export const HelpCircle = icon('HelpCircle', 'help-circle')
export const History = icon('History', 'history')
export const Home = icon('Home', 'home')
export const Image = icon('Image', 'image')
export const Info = icon('Info', 'info')
export const ImageUp = icon('ImageUp', 'image-up')
export const Layers = icon('Layers', 'layers')
export const LayoutGrid = icon('LayoutGrid', 'layout-grid')
export const Link = icon('Link', 'link')
export const Link2 = icon('Link2', 'link')
export const LogOut = icon('LogOut', 'log-out')
export const MailCheck = icon('MailCheck', 'mail-check')
export const Map = icon('Map', 'map')
export const MapPin = icon('MapPin', 'map-pin')
export const Menu = icon('Menu', 'menu')
export const MessageCircle = icon('MessageCircle', 'message-circle')
export const Monitor = icon('Monitor', 'monitor')
export const Moon = icon('Moon', 'moon')
export const Newspaper = icon('Newspaper', 'newspaper')
export const Package = icon('Package', 'package')
export const Pencil = icon('Pencil', 'pencil')
export const Plus = icon('Plus', 'plus')
export const RefreshCw = icon('RefreshCw', 'refresh-cw')
export const Repeat = icon('Repeat', 'repeat')
export const Rocket = icon('Rocket', 'rocket')
export const Search = icon('Search', 'search')
export const Settings = icon('Settings', 'settings')
export const Share2 = icon('Share2', 'share')
export const Shield = icon('Shield', 'shield')
export const ShieldAlert = icon('ShieldAlert', 'shield-alert')
export const ShieldCheck = icon('ShieldCheck', 'shield-check')
export const ShoppingBag = icon('ShoppingBag', 'shopping-bag')
export const ShoppingCart = icon('ShoppingCart', 'shopping-cart')
export const Store = icon('Store', 'store')
export const Sun = icon('Sun', 'sun')
export const Trash2 = icon('Trash2', 'trash2')
export const TrendingUp = icon('TrendingUp', 'trending-up')
export const Trophy = icon('Trophy', 'trophy')
export const Upload = icon('Upload', 'upload')
export const UserCheck = icon('UserCheck', 'user-check')
export const UserPlus = icon('UserPlus', 'user-plus')
export const Users = icon('Users', 'users')
export const Video = icon('Video', 'video')
export const Wallet = icon('Wallet', 'wallet')
export const X = icon('X', 'x')

export const ListChecks = icon('ListChecks', 'list-checks')
