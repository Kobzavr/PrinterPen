"""
i18n.py — Internationalization and localization for PrinterPen.
Provides dual-language support: English ('en') and Russian ('ru').
"""
from typing import Callable, Dict, List

# Active language (default is English)
_CURRENT_LANG = "en"

# Registered callbacks to trigger when language changes
_LISTENERS: List[Callable[[], None]] = []

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # ── Application ──────────────────────────────────────────
    "app_title": {
        "en": "PrinterPen",
        "ru": "PrinterPen",
    },
    "app_title_new": {
        "en": "PrinterPen — New Project",
        "ru": "PrinterPen — Новый проект",
    },
    "welcome_msg": {
        "en": "Welcome to PrinterPen!",
        "ru": "Добро пожаловать в PrinterPen!",
    },
    "new_project_created": {
        "en": "New project created",
        "ru": "Новый проект создан",
    },
    "unsaved_confirm": {
        "en": "Create a new project? All unsaved objects will be removed.",
        "ru": "Создать новый проект? Все несохранённые объекты будут удалены.",
    },
    "new_project": {
        "en": "New Project",
        "ru": "Новый проект",
    },
    "open_project": {
        "en": "Open Project...",
        "ru": "Открыть проект...",
    },
    "save_project": {
        "en": "Save Project",
        "ru": "Сохранить проект",
    },
    "save_project_as": {
        "en": "Save Project As...",
        "ru": "Сохранить проект как...",
    },
    "import_file": {
        "en": "Import File (SVG, Image)...",
        "ru": "Импорт файла (SVG, картинка)...",
    },
    "export_gcode": {
        "en": "Export G-code...",
        "ru": "Экспорт G-code...",
    },
    "export_svg": {
        "en": "Export to SVG...",
        "ru": "Экспорт в SVG...",
    },
    "exit": {
        "en": "Exit",
        "ru": "Выход",
    },

    # ── Menus ────────────────────────────────────────────────
    "menu_file": {"en": "File", "ru": "Файл"},
    "menu_edit": {"en": "Edit", "ru": "Правка"},
    "menu_view": {"en": "View", "ru": "Вид"},
    "menu_gcode": {"en": "G-code", "ru": "G-code"},
    "menu_language": {"en": "Language", "ru": "Язык"},
    "menu_theme": {"en": "Theme", "ru": "Тема"},
    "theme_dark": {"en": "Dark Theme", "ru": "Тёмная тема"},
    "theme_light": {"en": "Light Theme", "ru": "Светлая тема"},
    "tip_theme_toggle": {"en": "Switch between Dark and Light theme", "ru": "Переключить тёмную / светлую тему"},

    # Edit Menu Actions
    "action_delete_selected": {"en": "Delete Selected", "ru": "Удалить выбранное"},
    "action_settings": {"en": "Printer Settings...", "ru": "Настройки принтера..."},

    # View Menu Actions
    "action_fit_view": {"en": "Fit to Window", "ru": "По размеру окна"},
    "action_preview_gcode": {"en": "Show G-code Preview", "ru": "Показать превью G-code"},
    "action_show_grid": {"en": "Show Millimeter Grid", "ru": "Показать миллиметровую сетку"},

    # G-code Menu Actions
    "action_generate_gcode": {"en": "Generate G-code", "ru": "Сгенерировать G-code"},
    "action_send_to_printer": {"en": "Send to Printer", "ru": "Отправить на печать"},
    "action_test_patterns": {"en": "Test Patterns", "ru": "Тестовые паттерны"},
    "test_border": {"en": "Work Area Border", "ru": "Прямоугольник по краям"},
    "test_crosshair": {"en": "Center Crosshair", "ru": "Крест в центре"},
    "test_grid": {"en": "5×5 Grid", "ru": "Сетка 5×5"},
    "test_spiral": {"en": "Spiral", "ru": "Спираль"},

    # ── Docks ────────────────────────────────────────────────
    "dock_toolbox": {"en": "Tools", "ru": "Инструменты"},
    "dock_properties": {"en": "Properties", "ru": "Свойства"},
    "dock_connection": {"en": "Printer Connection", "ru": "Подключение к принтеру"},

    # ── Toolbox Panel ────────────────────────────────────────
    "tool_text": {"en": "Add Text", "ru": "Добавить текст"},
    "tool_text_active": {"en": "Click Canvas", "ru": "Кликните на холст"},
    "tool_text_tip": {
        "en": "Click on canvas to place editable text",
        "ru": "Нажмите на холст чтобы разместить текст",
    },
    "tool_image": {"en": "Add Image / SVG", "ru": "Изображение / SVG"},
    "tool_image_tip": {
        "en": "Import vector SVG or raster image (PNG, JPG, BMP)",
        "ru": "Импорт векторного SVG или растрового изображения (PNG, JPG, BMP)",
    },
    "tool_delete": {"en": "Delete Selected", "ru": "Удалить выбранное"},
    "tool_delete_tip": {"en": "Delete selected object (Delete)", "ru": "Удалить выбранный объект (Delete)"},
    "tool_fit": {"en": "Fit to Window", "ru": "По размеру экрана"},
    "tool_fit_tip": {"en": "Scale view to fit work area", "ru": "Масштабировать вид по рабочей области"},
    "tool_grid": {"en": "Grid", "ru": "Сетка"},
    "tool_grid_tip": {
        "en": "Toggle millimeter grid (Ctrl+G)\nCentimeter lines at overview, 1 mm lines when zoomed in",
        "ru": "Включить/выключить миллиметровую сетку (Ctrl+G)\nСантиметры при общем виде, 1 мм при приближении",
    },
    "nav_hints": {
        "en": "Navigation:\n• Scroll wheel — Zoom\n• Middle click — Pan\n• Left click — Select / Move\n• Drag handles — Rotate / Scale (Shift: 45°)",
        "ru": "Навигация:\n• Колёсико — Зум\n• Средняя кнопка — Перемещение\n• Клик — Выбор / Сдвиг\n• Маркеры — Поворот / Масштаб (Shift: 45°)",
    },

    # ── Properties Panel ─────────────────────────────────────
    "prop_title": {"en": "Properties", "ru": "Свойства"},
    "prop_empty": {"en": "Select an object\non canvas", "ru": "Выберите объект\nна холсте"},
    "chk_lock": {"en": "Lock", "ru": "Заблокировать"},
    "tip_lock": {
        "en": "Lock position, rotation, and size on canvas",
        "ru": "Заблокировать перемещение и трансформацию объекта",
    },
    "chk_hide": {"en": "Hide from G-code", "ru": "Скрыть из печати"},
    "tip_hide": {
        "en": "Exclude from G-code generation (remains as visual guide on canvas)",
        "ru": "Исключить из генерации G-code (остаётся как полупрозрачный ориентир)",
    },
    "btn_print_now": {"en": "Print Now", "ru": "Начать печать"},
    "btn_save_gcode": {"en": "Save to File...", "ru": "Сохранить в файл..."},
    "prop_type_text": {"en": "Type: Text", "ru": "Тип: Текст"},
    "prop_type_svg": {"en": "Type: SVG Image", "ru": "Тип: SVG изображение"},
    "prop_type_raster": {"en": "Type: Raster Image", "ru": "Тип: Растровое изображение"},

    "group_text": {"en": "Text Content", "ru": "Содержимое текста"},
    "lbl_text": {"en": "Text:", "ru": "Текст:"},
    "lbl_font": {"en": "Font:", "ru": "Шрифт:"},
    "btn_open_fonts": {"en": "", "ru": ""},
    "tip_open_fonts": {
        "en": "Open fonts folder (drop custom .ttf or .otf files here)",
        "ru": "Открыть папку со шрифтами (закиньте сюда файлы .ttf или .otf)",
    },
    "action_open_fonts": {"en": "Open Fonts Folder...", "ru": "Открыть папку со шрифтами..."},
    "msg_new_fonts_loaded": {"en": "New font(s) loaded: {names}", "ru": "Загружены новые шрифты: {names}"},
    "chk_bold": {"en": "Bold", "ru": "Жирный"},
    "chk_italic": {"en": "Italic", "ru": "Курсив"},

    "group_position": {"en": "Position", "ru": "Позиция"},
    "group_rotation": {"en": "Rotation", "ru": "Поворот"},
    "lbl_angle": {"en": "Angle:", "ru": "Угол:"},
    "group_scale": {"en": "Scale", "ru": "Масштаб"},
    "lbl_scale": {"en": "Scale:", "ru": "Масштаб:"},

    "group_vectorization": {"en": "Vectorization", "ru": "Векторизация"},
    "lbl_method": {"en": "Method:", "ru": "Метод:"},
    "method_canny": {"en": "Canny Edge Detection", "ru": "Грани Canny"},
    "method_smooth_contour": {"en": "Smooth Contour Trace", "ru": "Плавные контуры"},
    "method_centerline": {"en": "Centerline / Skeleton", "ru": "Осевая линия (скелет)"},
    "tip_method_centerline": {
        "en": "Traces a single stroke down the center of lines (ideal for line drawings, handwriting, sketches)",
        "ru": "Проводит одну линию по центру штриха (для скетчей, рукописного текста, чертежей)",
    },
    "chk_merge_close": {"en": "Merge lines closer than pen", "ru": "Объединять линии ближе пера"},
    "tip_merge_close": {
        "en": "Bridges parallel lines and narrow gaps closer than pen width into a single centerline pass",
        "ru": "Сливает параллельные линии и зазоры ближе толщины ручки в один центральный проход",
    },
    "lbl_min_path_len": {"en": "Min Line Length:", "ru": "Мин. длина линии:"},
    "tip_min_path_len": {
        "en": "Filter out speckles, dots and micro-strokes shorter than this length (mm)",
        "ru": "Игнорировать точки, пыль и микро-штрихи короче указанной длины (мм)",
    },

    "lbl_contour_thresh": {"en": "Brightness Cutoff:", "ru": "Порог яркости:"},
    "chk_auto_otsu": {"en": "Auto Cutoff (Otsu)", "ru": "Авто-порог (Otsu)"},
    "chk_invert_colors": {"en": "Invert (Dark BG)", "ru": "Инверсия (тёмный фон)"},
    "lbl_smoothness": {"en": "Curve Smoothness:", "ru": "Сглаживание кривых:"},
    "smooth_none": {"en": "Off (Angular)", "ru": "Без сглаживания"},
    "smooth_low": {"en": "Low (Subtle)", "ru": "Лёгкое"},
    "smooth_medium": {"en": "Medium (Smooth)", "ru": "Среднее (гладкие кривые)"},
    "smooth_high": {"en": "High (Ultra-round)", "ru": "Высокое (круги и дуги)"},

    "group_infill": {"en": "Area Infill / Hatching", "ru": "Закрашивание областей"},
    "chk_enable_infill": {"en": "Fill Solid Dark Regions", "ru": "Закрашивать тёмные области"},
    "lbl_infill_pattern": {"en": "Pattern:", "ru": "Паттерн:"},
    "pattern_linear": {"en": "Linear Hatch (Diagonal)", "ru": "Косые линии (штриховка)"},
    "pattern_crosshatch": {"en": "Cross-Hatch (Grid)", "ru": "Перекрёстная сетка"},
    "pattern_concentric": {"en": "Concentric Inset (Shells)", "ru": "Концентрический офсет внутрь"},
    "pattern_honeycomb": {"en": "Honeycomb (Hexagons)", "ru": "Соты (шестиугольники)"},
    "pattern_triangles": {"en": "Triangle Mesh", "ru": "Треугольная сетка"},
    "pattern_adaptive": {"en": "Adaptive Tonal (Shading)", "ru": "Адаптивная (по тонам / теням)"},
    "lbl_adaptive_range": {"en": "Shadow Range:", "ru": "Диапазон теней:"},
    "tip_adaptive_range": {
        "en": "Tonal range for adaptive infill (20–240, default 128).\nSlide left to make drawing lighter (dense lines only in darkest areas).\nSlide right to make shading deeper and darker.",
        "ru": "Диапазон теней для адаптивной заливки (20–240, по умолчанию 128).\nСдвиг влево осветляет рисунок (тени наносятся только на самые тёмные участки).\nСдвиг вправо делает затенение глубже и темнее.",
    },
    "lbl_infill_spacing": {"en": "Spacing / Cell size:", "ru": "Шаг линий / размер:"},
    "tip_infill_spacing": {
        "en": "Line pitch in mm. Set to pen tip diameter (e.g. 0.5 mm) for solid fill, or higher for open hatching.",
        "ru": "Шаг между линиями в мм. Равен толщине ручки для плотной заливки, либо больше для штриховки.",
    },
    "lbl_infill_angle": {"en": "Angle:", "ru": "Угол наклона:"},
    "lbl_infill_min_area": {"en": "Min Area:", "ru": "Мин. площадь:"},
    "tip_infill_min_area": {
        "en": "Minimum area in mm² to fill. Ignores thin outlines and fills only solid shapes (cat eyes, thick fonts, plates).",
        "ru": "Минимальная площадь в мм² для заливки. Игнорирует тонкие контуры и заливает только крупные области (глаза, залитый текст).",
    },
    "btn_infill_help": {"en": "💡 Infill Guide", "ru": "💡 О заливке"},
    "infill_help_title": {"en": "Infill Patterns Guide", "ru": "Руководство по закрашиванию областей"},
    "infill_help_content": {
        "en": (
            "<b>Area Infill Patterns:</b><br><br>"
            "• <b>Linear Hatch:</b> Parallel diagonal lines connected in serpentine zig-zag. Ideal for solid filling.<br>"
            "• <b>Cross-Hatch:</b> Two crossing passes at 90° for rich textured shading.<br>"
            "• <b>Concentric Inset:</b> Progressively offsets the outer contour inward by pen width. Creates very organic, clean fills with zero wasted moves.<br>"
            "• <b>Honeycomb / Triangles:</b> Geometric wireframe mesh clipped strictly inside solid black regions.<br>"
            "• <b>Adaptive Tonal:</b> Brightness-modulated density (denser lines in shadows, sparser in mid-tones, cross-hatch in deep shadows).<br><br>"
            "<b>Spacing:</b> Set to pen diameter (e.g. 0.5mm) for solid black, or 1.5–3mm for decorative hatching."
        ),
        "ru": (
            "<b>Типы закрашивания областей:</b><br><br>"
            "• <b>Косые линии:</b> Параллельная штриховка с непрерывной змейкой (минимум подъёмов ручки). Идеально для плотного закрашивания.<br>"
            "• <b>Перекрёстная сетка:</b> Двойная штриховка под углом 90° для насыщенного тона.<br>"
            "• <b>Концентрический офсет:</b> Заполнение последовательными контурами внутрь. Самый естественный способ для ручки плоттера.<br>"
            "• <b>Соты / Треугольники:</b> Геометрическая сетка, строго ограниченная границами тёмной области.<br>"
            "• <b>Адаптивная (по тонам / теням):</b> Варьирует плотность линий по яркости (густые линии в тенях, редкие в полутонах, сетка в глубоких тенях).<br><br>"
            "<b>Плотность:</b> Установите равной толщине ручки (например, 0.5 мм) для сплошного закрашивания, или 1.5–3 мм для штриховки."
        ),
    },

    "group_text_infill": {"en": "Letter Infill / Hatching", "ru": "Закрашивание / штриховка букв"},
    "chk_enable_text_infill": {"en": "Fill Letter Glyphs", "ru": "Заполнять буквы штриховкой"},

    "group_color_infill": {"en": "Color Infill Palette", "ru": "Палитра заливки по цветам"},
    "chk_enable_svg_infill": {"en": "Enable Vector Infill", "ru": "Включить штриховку вектора"},
    "lbl_color_swatch": {"en": "Color", "ru": "Цвет"},
    "lbl_color_fill": {"en": "Fill", "ru": "Заливка"},
    "lbl_color_pattern": {"en": "Pattern", "ru": "Узор"},
    "lbl_color_angle": {"en": "Angle", "ru": "Угол"},
    "lbl_scanning_colors": {"en": "Detecting colors...", "ru": "Определение цветов..."},
    "lbl_no_colors": {"en": "No filled areas detected", "ru": "Залитые области не найдены"},

    "group_canny": {"en": "Canny Parameters", "ru": "Параметры Canny"},
    "canny_group_tip": {
        "en": "Canny edge detection extracts paths for the plotter pen.",
        "ru": "Алгоритм Canny выделяет границы и переводит их в траектории для ручки плоттера.",
    },
    "lbl_thresh1": {"en": "Threshold 1 (details):", "ru": "Порог 1 (детали):"},
    "tip_thresh1": {
        "en": "Lower threshold: sensitivity to fine lines. Lower = more details.",
        "ru": "Порог 1 (нижний): чувствительность. Меньше = больше мелких деталей.",
    },
    "lbl_thresh2": {"en": "Threshold 2 (edges):", "ru": "Порог 2 (границы):"},
    "tip_thresh2": {
        "en": "Upper threshold: edge filtering. Higher = cleaner contours.",
        "ru": "Порог 2 (верхний): фильтр шума. Больше = чище контур.",
    },
    "chk_preview_lines": {"en": "Show line preview", "ru": "Показать превью линий"},
    "tip_preview_lines": {
        "en": "Displays red contour strokes and cyan infill paths over the image",
        "ru": "Отображает красные контуры и бирюзовые линии заливки поверх картинки",
    },
    "btn_canny_help": {"en": "💡 Tuning Tips", "ru": "💡 Как настраивать?"},
    "canny_help_title": {"en": "Vectorization Guide", "ru": "Подсказка по векторизации"},
    "canny_help_content": {
        "en": (
            "<b>Vectorization Methods Guide:</b><br><br>"
            "• <b>Centerline / Skeleton:</b> Traces a single stroke down the middle of lines without double outlines. Ideal for handwriting, sketches, line drawings, and wireframes.<br>"
            "• <b>Smooth Contours:</b> Traces outer and inner borders of filled shapes with organic curves. Ideal for logos, icons, and solid silhouettes.<br>"
            "• <b>Canny Edge:</b> Dual-threshold gradient detector. Ideal for photos, pencil art, and shaded drawings.<br><br>"
            "<b>Pen-Width & Noise Tips:</b><br>"
            "• Enable <i>'Merge lines closer than pen'</i> to collapse close parallel strokes into a single clean pass.<br>"
            "• Increase <i>'Min Line Length'</i> (e.g. 0.5–1.0 mm) to eliminate tiny noise specks and dust."
        ),
        "ru": (
            "<b>Руководство по векторизации:</b><br><br>"
            "• <b>Осевая линия (скелет):</b> Проводит одну центральную линию по штрихам без паразитных двойных контуров. Идеально для скетчей, рукописного текста, чертежей и линейной графики.<br>"
            "• <b>Плавные контуры:</b> Обводит внешние и внутренние границы залитых фигур плавными кривыми. Идеально для логотипов, иконок и силуэтов.<br>"
            "• <b>Грани Canny:</b> Двухпороговый детектор градиентов. Идеально для фотографий, штриховок и рисунков карандашом.<br><br>"
            "<b>Фильтрация и толщина пера:</b><br>"
            "• Включите <i>'Объединять линии ближе пера'</i>, чтобы близкие параллельные штрихи сливались в один центральный проход.<br>"
            "• Увеличьте <i>'Мин. длина линии'</i> (0.5–1.0 мм), чтобы убрать микро-точки и случайный мусор."
        ),
    },
    "lbl_auto_update": {"en": "← Sliders auto-update lines", "ru": "← Слайдеры авто-обновляют линии"},

    # ── Serial Panel ─────────────────────────────────────────
    "lbl_port": {"en": "Port:", "ru": "Порт:"},
    "btn_refresh": {"en": "", "ru": ""},
    "btn_refresh_tip": {"en": "Refresh COM ports list", "ru": "Обновить список COM портов"},
    "lbl_baudrate": {"en": "Baud:", "ru": "Скорость:"},
    "btn_connect": {"en": "Connect", "ru": "Подключиться"},
    "btn_disconnect": {"en": "Disconnect", "ru": "Отключиться"},
    "status_not_connected": {"en": "Status: Disconnected", "ru": "Статус: Не подключен"},
    "status_connected": {"en": "Status: Connected to {port}", "ru": "Статус: Подключен к {port}"},
    "btn_compile_gcode": {"en": "Compile G-code", "ru": "Скомпилировать G-code"},
    "tip_compile_gcode": {
        "en": "Compile all canvas objects into G-code commands and calculate command count",
        "ru": "Скомпилировать все объекты с холста в G-code и рассчитать количество команд",
    },
    "btn_print": {"en": "Start Print", "ru": "Начать печать"},
    "btn_pause": {"en": "Pause", "ru": "Пауза"},
    "btn_resume": {"en": "Resume", "ru": "Продолжить"},
    "btn_stop": {"en": "Stop", "ru": "Стоп"},
    "lbl_progress_initial": {"en": "0 / 0 commands", "ru": "0 / 0 команд"},
    "lbl_progress_format": {"en": "{current} / {total} commands ({percent}%)", "ru": "{current} / {total} команд ({percent}%)"},
    "lbl_est_time": {"en": "Est: ~{time}", "ru": "Время: ~{time}"},
    "lbl_rem_time": {"en": "Left: ~{time}", "ru": "Осталось: ~{time}"},
    "lbl_time_done": {"en": "Done", "ru": "Готово"},
    "group_log": {"en": "Commands Log", "ru": "Лог команд"},
    "btn_clear_log": {"en": "Clear Log", "ru": "Очистить лог"},

    # ── Canvas View & Rulers ─────────────────────────────────
    "canvas_work_area": {"en": "work area", "ru": "рабочая зона"},
    "canvas_printer": {"en": "Printer", "ru": "Принтер"},
    "canvas_offset_x": {"en": "Offset X", "ru": "Оффсет X"},
    "canvas_dead_zone": {"en": "Dead zone (pen offset)", "ru": "Недоступная зона: оффсет ручки"},
    "unit_mm": {"en": "mm", "ru": "мм"},

    # ── Settings Dialog ──────────────────────────────────────
    "settings_title": {"en": "Printer Settings — PrinterPen", "ru": "Настройки — PrinterPen"},
    "tab_general": {"en": "General & Pen", "ru": "Основные и ручка"},
    "tab_gcode": {"en": "Custom G-code", "ru": "Пользовательский G-code"},
    "tab_connection": {"en": "Connection", "ru": "Подключение"},
    "group_printer_area": {"en": "Physical Printer Area", "ru": "Физическая область принтера"},
    "lbl_printer_w": {"en": "Max Width X:", "ru": "Макс. ширина X:"},
    "lbl_printer_h": {"en": "Max Height Y:", "ru": "Макс. высота Y:"},
    "tip_printer_w": {"en": "Maximum X travel range from firmware", "ru": "Максимальная ширина перемещения по X (из прошивки)"},
    "tip_printer_h": {"en": "Maximum Y travel range from firmware", "ru": "Максимальная высота перемещения по Y"},

    "group_pen_offset": {"en": "Pen Offset (relative to nozzle)", "ru": "Оффсет ручки (относительно сопла)"},
    "offset_description": {
        "en": "The pen is offset from the nozzle.\nThis offset reduces the available drawing area.",
        "ru": "Ручка закреплена со смещением от сопла.\nОффсет уменьшает рабочую область холста.",
    },
    "lbl_offset_x": {"en": "X Offset:", "ru": "Оффсет X:"},
    "lbl_offset_y": {"en": "Y Offset:", "ru": "Оффсет Y:"},
    "tip_offset_x": {
        "en": "Positive = pen mounted to the RIGHT of nozzle (dead zone on left).\nNegative = pen mounted to the LEFT of nozzle (dead zone on right).",
        "ru": "Положительное = ручка СПРАВА от сопла (мертвая зона слева).\nОтрицательное = ручка СЛЕВА от сопла (мертвая зона справа).",
    },
    "tip_offset_y": {
        "en": "Positive = dead zone at top (coordinates 0..Y).\nNegative = dead zone at bottom.",
        "ru": "Положительное = мертвая зона сверху (координаты от 0 до Y).\nОтрицательное = мертвая зона снизу.",
    },

    "group_z_axis": {"en": "Z Axis (drawing height & pressure)", "ru": "Ось Z (высота рисования и прижим)"},
    "lbl_pen_z_offset": {"en": "Pen Z Mount Offset:", "ru": "Ручка ниже сопла на:"},
    "tip_pen_z_offset": {
        "en": "Physical distance between pen tip and nozzle (mm).\nPen MUST be lower than nozzle to prevent scraping.",
        "ru": "Физическое расстояние кончика ручки ниже сопла (мм).\nРучка должна быть ниже чтобы сопло не царапало стол.",
    },
    "lbl_z_draw_offset": {"en": "Pressure Fine-tune:", "ru": "Подстройка прижима:"},
    "tip_z_draw_offset": {
        "en": "> 0: pen higher (gentle touch)\n0: exact contact\n< 0: press into paper (firm pens)",
        "ru": "> 0: ручка выше (меньше нажим)\n0: точный контакт\n< 0: вдавливание (для тугих ручек)",
    },
    "lbl_z_lift": {"en": "Travel Lift:", "ru": "Подъём при переезде:"},
    "tip_z_lift": {
        "en": "How high pen lifts above paper during rapid travel moves",
        "ru": "На сколько мм ручка поднимается над бумагой при переездах",
    },
    "lbl_pen_width": {"en": "Pen Tip Diameter:", "ru": "Толщина пишущего узла:"},
    "tip_pen_width": {
        "en": "Diameter of the pen tip / ball (mm). Used for preview and stroke optimization.",
        "ru": "Диаметр шарика/пера ручки (мм). Используется для превью и оптимизации близких линий.",
    },

    "group_orientation": {"en": "Orientation", "ru": "Ориентация"},
    "chk_invert_y": {"en": "Invert Y axis (Canvas top = Printer back)", "ru": "Инвертировать ось Y (верх холста = дальний край стола)"},
    "tip_invert_y": {
        "en": "Printer Y=0 is front edge, canvas Y=0 is top.\nEnabled by default for natural orientation.",
        "ru": "На принтере Y=0 спереди, на экране Y=0 сверху.\nВключите чтобы рисунок не был перевернут.",
    },

    "group_speeds": {"en": "Speeds (mm/min)", "ru": "Скорости (мм/мин)"},
    "lbl_speed_travel": {"en": "Travel Speed:", "ru": "Скорость переезда (G0):"},
    "lbl_speed_draw": {"en": "Draw Speed:", "ru": "Скорость рисования (G1):"},

    "group_custom_gcode": {"en": "Custom G-code (Header & Footer)", "ru": "Пользовательский G-code (Header и Footer)"},
    "lbl_gcode_header": {"en": "Initialization G-code (Header):", "ru": "Команды запуска (Header):"},
    "lbl_gcode_footer": {"en": "Finish G-code (Footer):", "ru": "Команды завершения (Footer):"},
    "btn_reset_gcode": {"en": "Reset to Defaults", "ru": "Сбросить на стандартные"},
    "gcode_variables_hint": {
        "en": "Available variables: {z_up}, {z_down}, {f_travel}, {f_draw}, {canvas_w}, {canvas_h}",
        "ru": "Доступные переменные: {z_up}, {z_down}, {f_travel}, {f_draw}, {canvas_w}, {canvas_h}",
    },

    "group_calculated": {"en": "Calculated Values", "ru": "Итоговые параметры"},
    "lbl_calc_canvas": {"en": "Working Canvas Area:", "ru": "Размер рабочего холста:"},
    "lbl_calc_z_down": {"en": "Drawing Z Position:", "ru": "Z рисования (G1):"},
    "lbl_calc_z_up": {"en": "Travel Z Position:", "ru": "Z переезда (G0):"},
}


def get_language() -> str:
    """Returns the currently active language code ('en' or 'ru')."""
    return _CURRENT_LANG


def set_language(lang: str):
    """Sets the active language code and notifies all registered UI listeners."""
    global _CURRENT_LANG
    if lang in ("en", "ru") and lang != _CURRENT_LANG:
        _CURRENT_LANG = lang
        for callback in _LISTENERS:
            try:
                callback()
            except Exception:
                pass


def register_listener(callback: Callable[[], None]):
    """Registers a UI update callback invoked whenever the language changes."""
    if callback not in _LISTENERS:
        _LISTENERS.append(callback)


def unregister_listener(callback: Callable[[], None]):
    """Unregisters a UI update callback."""
    if callback in _LISTENERS:
        _LISTENERS.remove(callback)


def tr(key: str, **kwargs) -> str:
    """
    Translates a key into the active language string.
    Supports formatted substitutions, e.g. tr('status_connected', port='COM3').
    """
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key
    text = entry.get(_CURRENT_LANG, entry.get("en", key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text
