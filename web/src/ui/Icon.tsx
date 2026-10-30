import { IconAlertTriangle, IconArrowBackUp, IconCheck, IconCopy, IconDeviceFloppy, IconInfoCircle, IconListSearch, IconLogin, IconLogout, IconBolt, IconPencil, IconPlus, IconRefresh, IconSearch, IconTrash, IconX, IconArrowsMaximize, IconBooks, IconBook, IconDownload, IconHierarchy2, IconInbox, IconLayoutDashboard, IconListDetails, IconMessageQuestion,
  IconBook2, IconBrandGit, IconFileText, IconMessagePlus, IconMoon, IconPhoto, IconUpload, IconPlayerPause, IconPlayerPlay, IconSettings, IconSun, IconTags, IconTerminal2, IconTimeline, IconListCheck, IconFolder, IconArrowUp, IconArrowDown, IconSelector, IconFilter, IconBell, IconPinnedOff } from "@tabler/icons-react";
import type { ComponentType } from "react";

/** Iconos de la aplicación (Tabler Icons, MIT). Un solo trazo y un solo tamaño por defecto; las pantallas piden un icono por nombre. */
const ICONS = {
  overview: IconLayoutDashboard, ask: IconMessageQuestion, proposals: IconInbox, journal: IconBook, facts: IconListDetails, timeline: IconTimeline,
  docs: IconBook2, repo: IconBrandGit, feedback: IconMessagePlus, knowledge: IconFileText, upload: IconUpload, graph: IconHierarchy2, vocabulary: IconBooks, types: IconTags, query: IconTerminal2, admin: IconSettings,
  search: IconSearch, check: IconCheck, close: IconX, plus: IconPlus, edit: IconPencil, trash: IconTrash, copy: IconCopy, test: IconBolt, refresh: IconRefresh,
  save: IconDeviceFloppy, logout: IconLogout, login: IconLogin, models: IconListSearch, info: IconInfoCircle, alert: IconAlertTriangle,
  sortUp: IconArrowUp, sortDown: IconArrowDown, sortNone: IconSelector, filter: IconFilter, jobs: IconListCheck, folder: IconFolder, play: IconPlayerPlay, pause: IconPlayerPause, undo: IconArrowBackUp, download: IconDownload, image: IconPhoto, fit: IconArrowsMaximize, sun: IconSun, moon: IconMoon, bell: IconBell, unpin: IconPinnedOff,
} as const;
export type IconName = keyof typeof ICONS;

export function Icon({ name, size = 18, stroke = 1.75 }: { name: IconName; size?: number; stroke?: number }) {
  const C = ICONS[name] as ComponentType<{ size?: number; stroke?: number; "aria-hidden"?: boolean }>;
  return <C size={size} stroke={stroke} aria-hidden />;
}
