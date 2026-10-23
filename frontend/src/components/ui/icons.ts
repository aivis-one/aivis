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
// A key the set does not have stays the lucide icon, re-exported at the end
// (a GAP, listed in the build record): ListChecks.
// =============================================================================

import { defineComponent, h } from 'vue'

export function icon(name: string, key: string) {
  return defineComponent({
    name,
    props: { size: { type: [Number, String], default: 24 } },
    setup(props) {
      return () =>
        h(
          'svg',
          {
            class: 'ds-icon',
            'aria-hidden': 'true',
            viewBox: '0 0 24 24',
            style: { inlineSize: props.size + 'px', blockSize: props.size + 'px' },
          },
          [h('use', { href: '#i-' + key })],
        )
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
export const Ghost = icon('Ghost', 'ghost')
export const Gift = icon('Gift', 'gift')
export const HelpCircle = icon('HelpCircle', 'help-circle')
export const History = icon('History', 'history')
export const Home = icon('Home', 'home')
export const Image = icon('Image', 'image')
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

// Not in the system's set.
export { ListChecks } from 'lucide-vue-next'
