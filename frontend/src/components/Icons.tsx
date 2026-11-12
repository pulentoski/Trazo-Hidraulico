// Íconos de la interfaz: un solo set (Lucide), mismo tamaño y grosor en todo el sistema (docs/estilo.md).
// El tamaño lo fija el CSS (--icon); el grosor, ICON_STROKE. Se usan como <Icon.save />.
import type { LucideIcon } from "lucide-react";
import {
  Activity, ArrowDownUp, ArrowLeft, Building2, ChartColumn, Check, ChevronDown, ChevronLeft, ChevronRight, CircleDot,
  CircleSlash2, Clock, Crosshair, Cylinder, Download, Drill, Ellipsis, FileSpreadsheet, FileUp, FireExtinguisher,
  FolderOpen, History, House, HousePlug, Info, Layers, LayoutDashboard, LogOut, MapPin, Maximize2, Menu, Minus, Moon,
  MousePointer2, Move, Play, Plus, Redo2, Ruler, Save, Search, Settings, Spline, Square, SquareDashedMousePointer, Sun,
  Table2, Tag, Trash2, TriangleAlert, Undo2, Upload, User, Users, Waves, Wrench, X,
} from "lucide-react";

export const ICON_STROKE = 1.75;

const make = (C: LucideIcon) => {
  const I = () => <C strokeWidth={ICON_STROKE} aria-hidden="true" focusable="false" />;
  I.displayName = C.displayName;
  return I;
};

export const Icon = {
  // Herramientas del editor
  select: make(MousePointer2),
  multi: make(SquareDashedMousePointer),
  move: make(Move),
  junction: make(CircleDot),
  pipe: make(Spline),
  tank: make(Cylinder),
  reservoir: make(Waves),
  well: make(Drill),
  shutoff: make(CircleSlash2),
  hydrant: make(FireExtinguisher),
  client: make(HousePlug),
  feasibility: make(Crosshair),
  measure: make(Ruler),
  trash: make(Trash2),
  // Archivo, vistas y análisis
  save: make(Save),
  history: make(History),
  undo: make(Undo2),
  redo: make(Redo2),
  summary: make(LayoutDashboard),
  gestion: make(ChartColumn),
  play: make(Play),
  download: make(Download),
  upload: make(Upload),
  fileUp: make(FileUp),
  folder: make(FolderOpen),
  table: make(Table2),
  csv: make(FileSpreadsheet),
  layers: make(Layers),
  search: make(Search),
  tag: make(Tag),
  // Navegación y cuenta
  back: make(ArrowLeft),
  menu: make(Menu),
  home: make(House),
  gear: make(Settings),
  user: make(User),
  users: make(Users),
  org: make(Building2),
  logout: make(LogOut),
  sun: make(Sun),
  moon: make(Moon),
  // Genéricos
  info: make(Info),
  plus: make(Plus),
  close: make(X),
  check: make(Check),
  more: make(Ellipsis),
  chevronDown: make(ChevronDown),
  chevronRight: make(ChevronRight),
  chevronLeft: make(ChevronLeft),
  sort: make(ArrowDownUp),
  alert: make(TriangleAlert),
  clock: make(Clock),
  pin: make(MapPin),
  wrench: make(Wrench),
  activity: make(Activity),
  minus: make(Minus),
  square: make(Square),
  maximize: make(Maximize2),
};
