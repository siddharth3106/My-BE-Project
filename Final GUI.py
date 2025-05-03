import serial.tools.list_ports
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib as mpl
from datetime import datetime, timedelta
import time
import os
import threading
import json
import traceback
from scipy import stats
import csv

class TemperaturePressureLogger:
    def __init__(self, root):
        # Configuration
        self.serial_port = None
        self.baud_rate = 9600
        self.ser = None
        self.config_file = "tpl_config.json"
        
        # App state
        self.is_recording = False
        self.is_paused = False
        self.time_counter = 0
        self.start_time = None
        self.connection_active = False
        self.auto_reconnect = True
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.last_data_time = None
        self.outlier_detection_enabled = True
        self.outlier_threshold = 3.0  # Standard deviations
        
        # Data storage
        self.temperature_data = []
        self.pressure_data = []
        self.time_stamps = []
        self.datetime_stamps = []
        self.backup_interval = 60  # seconds
        self.last_backup_time = time.time()
        
        # Advanced statistics
        self.temp_delta = []
        self.press_delta = []
        self.forecast_horizon = 10  # seconds
        
        # Visualization settings
        self.plot_mode = "line"  # line, scatter, both
        self.time_window = 60  # seconds to display in rolling window
        self.show_statistics_overlay = True
        self.show_data_labels = False
        
        # Color scheme
        self.bg_color = "#1E1E2E"  # Dark background
        self.accent_color = "#94E2D5"  # Teal accent
        self.secondary_accent = "#F5C2E7"  # Pink accent
        self.text_color = "#CDD6F4"  # Light text
        self.temp_color = "#FAB387"  # Orange for temperature
        self.pressure_color = "#89B4FA"  # Blue for pressure
        self.highlight_color = "#F38BA8"  # Red highlight
        self.success_color = "#A6E3A1"  # Green success
        self.warning_color = "#F9E2AF"  # Yellow warning
        
        # Load saved settings
        self.load_config()
        
        # Setup the root window
        self.root = root
        self.setup_ui()
        
        # Set up watchdog timer for data integrity
        self.watchdog_timer = None
        self.setup_watchdog()
        
        # Attempt to auto-detect ports
        self.refresh_ports()
        
    def setup_ui(self):
        """Setup the user interface"""
        self.root.title("Temperature & Pressure Monitoring System")
        self.root.geometry("1280x900")
        self.root.configure(bg=self.bg_color)
        self.root.minsize(1000, 700)
        
        # Set application icon if available
        try:
            self.root.iconbitmap("tpl_icon.ico")
        except:
            pass
        
        # Configure the ttk style
        self.configure_styles()
        
        # Create a tab control for more organized UI
        self.tab_control = ttk.Notebook(self.root)
        self.tab_control.pack(expand=1, fill="both")
        
        # Create tabs
        self.main_tab = ttk.Frame(self.tab_control)
        self.analysis_tab = ttk.Frame(self.tab_control)
        self.settings_tab = ttk.Frame(self.tab_control)
        
        self.tab_control.add(self.main_tab, text="Monitoring")
        self.tab_control.add(self.analysis_tab, text="Analysis")
        self.tab_control.add(self.settings_tab, text="Settings")
        
        # Set up main tab
        self.setup_main_tab()
        
        # Set up analysis tab
        self.setup_analysis_tab()
        
        # Set up settings tab
        self.setup_settings_tab()
        
        # Create status bar (global across all tabs)
        self.create_status_bar()
        
        # Bind tab change event
        self.tab_control.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        
        # Set up error logging
        self.error_log = []
        
        # Bind window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def configure_styles(self):
        """Configure ttk styles for widgets"""
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Configure colors and fonts for widgets
        self.style.configure("TFrame", background=self.bg_color)
        self.style.configure("TNotebook", background=self.bg_color)
        self.style.configure("TNotebook.Tab", background=self.bg_color, foreground=self.text_color, padding=[10, 2])
        self.style.map("TNotebook.Tab", background=[("selected", self.accent_color)], 
                      foreground=[("selected", self.bg_color)])
        
        self.style.configure("Header.TLabel", background=self.bg_color, foreground=self.text_color, font=("Segoe UI", 24, "bold"))
        self.style.configure("SubHeader.TLabel", background=self.bg_color, foreground=self.text_color, font=("Segoe UI", 14))
        self.style.configure("Stats.TLabel", background=self.bg_color, foreground=self.text_color, font=("Segoe UI", 12))
        self.style.configure("Alert.TLabel", background=self.bg_color, foreground=self.highlight_color, font=("Segoe UI", 12, "bold"))
        self.style.configure("Success.TLabel", background=self.bg_color, foreground=self.success_color, font=("Segoe UI", 12))
        
        # Button styles
        self.style.configure("TButton", background=self.bg_color, foreground=self.text_color, borderwidth=1, font=("Segoe UI", 10))
        self.style.map("TButton", background=[("active", self.accent_color)], foreground=[("active", self.bg_color)])
        
        self.style.configure("Start.TButton", background=self.accent_color, foreground=self.bg_color, font=("Segoe UI", 12, "bold"))
        self.style.configure("Stop.TButton", background=self.highlight_color, foreground=self.bg_color, font=("Segoe UI", 12, "bold"))
        self.style.configure("Export.TButton", background=self.secondary_accent, foreground=self.bg_color, font=("Segoe UI", 12, "bold"))
        self.style.configure("Accent.TButton", background=self.accent_color, foreground=self.bg_color, font=("Segoe UI", 11))
        
        # Table styles
        self.style.configure("Treeview", 
                            background=self.bg_color, 
                            foreground=self.text_color, 
                            rowheight=25, 
                            fieldbackground=self.bg_color,
                            font=("Segoe UI", 11))
        self.style.configure("Treeview.Heading", 
                            background=self.accent_color, 
                            foreground=self.bg_color, 
                            font=("Segoe UI", 12, "bold"))
        self.style.map('Treeview', background=[('selected', self.secondary_accent)], foreground=[('selected', self.bg_color)])
        
        # Separator
        self.style.configure("TSeparator", background=self.text_color)
        
        # Checkbox and radio buttons
        self.style.configure("TCheckbutton", background=self.bg_color, foreground=self.text_color, font=("Segoe UI", 12))
        self.style.configure("TRadiobutton", background=self.bg_color, foreground=self.text_color, font=("Segoe UI", 12))
        self.style.map("TCheckbutton", background=[("active", self.bg_color)], foreground=[("active", self.accent_color)])
        self.style.map("TRadiobutton", background=[("active", self.bg_color)], foreground=[("active", self.accent_color)])
        
        # Combobox
        self.style.configure("TCombobox", background=self.bg_color, fieldbackground=self.bg_color, foreground=self.text_color)
        self.style.map("TCombobox", fieldbackground=[("readonly", self.bg_color)])
        self.style.map("TCombobox", selectbackground=[("readonly", self.accent_color)])
        self.style.map("TCombobox", selectforeground=[("readonly", self.bg_color)])
    
    def setup_main_tab(self):
        """Set up the main monitoring tab"""
        # Create the header section
        self.create_header_frame(self.main_tab)
        
        # Create top control panel
        top_frame = ttk.Frame(self.main_tab)
        top_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # Split top frame into left (controls) and right (stats)
        self.create_control_panel(top_frame)
        self.create_stats_panel(top_frame)
        
        # Create graph panel
        self.create_graph_panel(self.main_tab)
        
        # Create data table
        self.create_data_table(self.main_tab)
        
    def setup_analysis_tab(self):
        """Set up the data analysis tab"""
        # Create header for analysis tab
        header_frame = ttk.Frame(self.analysis_tab)
        header_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        ttk.Label(header_frame, text="Data Analysis & Statistics", style="Header.TLabel").pack(side=tk.LEFT)
        
        # Create statistics area
        self.create_advanced_stats_panel(self.analysis_tab)
        
        # Create additional visualization area
        self.create_advanced_visualization(self.analysis_tab)
    
    def setup_settings_tab(self):
        """Set up the settings tab"""
        settings_header_frame = ttk.Frame(self.settings_tab)
        settings_header_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        ttk.Label(settings_header_frame, text="Application Settings", style="Header.TLabel").pack(side=tk.LEFT)
        
        # Main settings container with scrollbar
        settings_canvas = tk.Canvas(self.settings_tab, bg=self.bg_color, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.settings_tab, orient="vertical", command=settings_canvas.yview)
        settings_canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        settings_canvas.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Frame inside canvas for scrolling
        settings_frame = ttk.Frame(settings_canvas)
        settings_canvas.create_window((0, 0), window=settings_frame, anchor='nw')
        
        # Connection settings
        self.create_connection_settings(settings_frame)
        
        # Data processing settings
        self.create_data_settings(settings_frame)
        
        # Display settings
        self.create_display_settings(settings_frame)
        
        # Application settings
        self.create_app_settings(settings_frame)
        
        # Update scrollregion when frame size changes
        settings_frame.bind("<Configure>", lambda e: settings_canvas.configure(scrollregion=settings_canvas.bbox("all")))
    
    def create_header_frame(self, parent):
        """Create the header section"""
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, padx=20, pady=(20, 0))
        
        title_label = ttk.Label(header_frame, text="Temperature & Pressure Monitoring System", style="Header.TLabel")
        title_label.pack(side=tk.LEFT, padx=10)
        
        # Connection status indicator
        self.connection_frame = ttk.Frame(header_frame)
        self.connection_frame.pack(side=tk.RIGHT, padx=10)
        
        self.connection_indicator = tk.Canvas(self.connection_frame, width=15, height=15, bg=self.bg_color, highlightthickness=0)
        self.connection_indicator.create_oval(2, 2, 13, 13, fill="red", tags="indicator")
        self.connection_indicator.pack(side=tk.LEFT, padx=(0, 5))
        
        self.connection_status = ttk.Label(self.connection_frame, text="Disconnected", style="Stats.TLabel")
        self.connection_status.pack(side=tk.LEFT, padx=5)
        
        # Current time display
        self.time_display = ttk.Label(header_frame, text="", style="SubHeader.TLabel")
        self.time_display.pack(side=tk.RIGHT, padx=10)
        self.update_time_display()
        
    def update_time_display(self):
        """Update the current time display"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_display.config(text=current_time)
        self.root.after(1000, self.update_time_display)
        
    def create_control_panel(self, parent):
        """Create the control panel with port selection and control buttons"""
        control_frame = ttk.Frame(parent)
        control_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        # Connection settings
        conn_frame = ttk.LabelFrame(control_frame, text="Connection Settings", padding=10)
        conn_frame.pack(fill=tk.X, pady=5)
        
        port_frame = ttk.Frame(conn_frame)
        port_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(port_frame, text="COM Port:", style="Stats.TLabel").pack(side=tk.LEFT, padx=5)
        
        # Dropdown for COM port selection
        self.port_var = tk.StringVar()
        self.port_dropdown = ttk.Combobox(port_frame, textvariable=self.port_var, width=15, state="readonly")
        self.port_dropdown.pack(side=tk.LEFT, padx=5)
        
        # Refresh ports button
        refresh_btn = ttk.Button(port_frame, text="🔄", width=3, command=self.refresh_ports)
        refresh_btn.pack(side=tk.LEFT, padx=5)
        
        # Show connection test button
        test_btn = ttk.Button(port_frame, text="Test Connection", command=self.test_connection)
        test_btn.pack(side=tk.LEFT, padx=5)
        
        # Recording controls frame
        rec_frame = ttk.LabelFrame(control_frame, text="Recording Controls", padding=10)
        rec_frame.pack(fill=tk.X, pady=10)
        
        btn_frame = ttk.Frame(rec_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        
        self.start_btn = ttk.Button(btn_frame, text="▶ Start", command=self.start_recording, style="Start.TButton", width=10)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.pause_btn = ttk.Button(btn_frame, text="⏸ Pause", command=self.pause_recording, style="TButton", width=10)
        self.pause_btn.pack(side=tk.LEFT, padx=5)
        self.pause_btn.config(state=tk.DISABLED)
        
        self.stop_btn = ttk.Button(btn_frame, text="■ Stop", command=self.stop_recording, style="Stop.TButton", width=10)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn.config(state=tk.DISABLED)
        
        # Data export controls
        export_frame = ttk.LabelFrame(control_frame, text="Data Export", padding=10)
        export_frame.pack(fill=tk.X, pady=5)
        
        self.export_btn = ttk.Button(export_frame, text="💾 Export to Excel", command=lambda: self.export_data("excel"), style="Export.TButton")
        self.export_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.export_csv_btn = ttk.Button(export_frame, text="📄 Export to CSV", command=lambda: self.export_data("csv"), style="Export.TButton")
        self.export_csv_btn.pack(side=tk.LEFT, padx=5, pady=5)
        
    def create_stats_panel(self, parent):
        """Create the statistics panel"""
        stats_frame = ttk.LabelFrame(parent, text="Live Statistics", padding=10)
        stats_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        
        # Temperature stats
        temp_frame = ttk.Frame(stats_frame)
        temp_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(temp_frame, text="🌡️ Temperature:", foreground=self.temp_color, style="SubHeader.TLabel").pack(anchor="w")
        
        self.temp_stats_var = tk.StringVar(value="Min: --°C | Max: --°C | Avg: --°C")
        ttk.Label(temp_frame, textvariable=self.temp_stats_var, style="Stats.TLabel").pack(anchor="w", padx=10)
        
        self.temp_current_var = tk.StringVar(value="Current: --°C | Change: --°C/min")
        ttk.Label(temp_frame, textvariable=self.temp_current_var, style="Stats.TLabel").pack(anchor="w", padx=10)
        
        # Pressure stats
        press_frame = ttk.Frame(stats_frame)
        press_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(press_frame, text="🔄 Pressure:", foreground=self.pressure_color, style="SubHeader.TLabel").pack(anchor="w")
        
        self.press_stats_var = tk.StringVar(value="Min: --hPa | Max: --hPa | Avg: --hPa")
        ttk.Label(press_frame, textvariable=self.press_stats_var, style="Stats.TLabel").pack(anchor="w", padx=10)
        
        self.press_current_var = tk.StringVar(value="Current: --hPa | Change: --hPa/min")
        ttk.Label(press_frame, textvariable=self.press_current_var, style="Stats.TLabel").pack(anchor="w", padx=10)
        
        # Record duration
        duration_frame = ttk.Frame(stats_frame)
        duration_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(duration_frame, text="⏱️ Recording Details:", style="SubHeader.TLabel").pack(anchor="w")
        
        self.duration_var = tk.StringVar(value="Duration: 00:00:00")
        ttk.Label(duration_frame, textvariable=self.duration_var, style="Stats.TLabel").pack(anchor="w", padx=10)
        
        self.sample_count_var = tk.StringVar(value="Samples: 0 | Rate: 0 samples/min")
        ttk.Label(duration_frame, textvariable=self.sample_count_var, style="Stats.TLabel").pack(anchor="w", padx=10)
        
        # Alert indicators
        alert_frame = ttk.Frame(stats_frame)
        alert_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(alert_frame, text="⚠️ Alerts:", style="SubHeader.TLabel").pack(anchor="w")
        
        self.alert_var = tk.StringVar(value="No alerts")
        self.alert_label = ttk.Label(alert_frame, textvariable=self.alert_var, style="Stats.TLabel")
        self.alert_label.pack(anchor="w", padx=10)
        
    def create_graph_panel(self, parent):
        """Create the graph display panel"""
        graph_frame = ttk.Frame(parent)
        graph_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Visualization controls
        viz_controls = ttk.Frame(graph_frame)
        viz_controls.pack(fill=tk.X, pady=5)
        
        # Plot type selection
        ttk.Label(viz_controls, text="Plot Type:", style="Stats.TLabel").pack(side=tk.LEFT, padx=5)
        
        self.plot_type_var = tk.StringVar(value="line")
        plot_type_combo = ttk.Combobox(viz_controls, textvariable=self.plot_type_var, width=10, state="readonly")
        plot_type_combo.pack(side=tk.LEFT, padx=5)
        plot_type_combo['values'] = ('line', 'scatter', 'both')
        plot_type_combo.bind("<<ComboboxSelected>>", lambda e: self.update_plots())
        
        # Time window selection
        ttk.Label(viz_controls, text="Time Window (s):", style="Stats.TLabel").pack(side=tk.LEFT, padx=5)
        
        self.time_window_var = tk.StringVar(value=str(self.time_window))
        time_window_combo = ttk.Combobox(viz_controls, textvariable=self.time_window_var, width=5, state="readonly")
        time_window_combo.pack(side=tk.LEFT, padx=5)
        time_window_combo['values'] = ('30', '60', '120', '300', '600', 'all')
        time_window_combo.bind("<<ComboboxSelected>>", self.update_time_window)
        
        # Show statistics overlay
        self.stat_overlay_var = tk.BooleanVar(value=self.show_statistics_overlay)
        stat_overlay_check = ttk.Checkbutton(viz_controls, text="Show Statistics Overlay", 
                                           variable=self.stat_overlay_var, command=self.update_plots)
        stat_overlay_check.pack(side=tk.LEFT, padx=15)
        
        # Show data labels
        self.data_labels_var = tk.BooleanVar(value=self.show_data_labels)
        data_labels_check = ttk.Checkbutton(viz_controls, text="Show Data Labels", 
                                          variable=self.data_labels_var, command=self.update_plots)
        data_labels_check.pack(side=tk.LEFT, padx=15)
        
        # Set up matplotlib figure with dark theme
        plt.style.use('dark_background')
        self.fig = plt.figure(figsize=(10, 5), facecolor=self.bg_color)
        
        # Create subplots with shared x-axis
        gs = self.fig.add_gridspec(2, 1, hspace=0.15)
        self.ax1 = self.fig.add_subplot(gs[0])
        self.ax2 = self.fig.add_subplot(gs[1], sharex=self.ax1)
        
        # Configure axes
        for ax in [self.ax1, self.ax2]:
            ax.tick_params(colors=self.text_color)
            ax.grid(True, alpha=0.3)
            ax.set_facecolor(self.bg_color)
            for spine in ax.spines.values():
                spine.set_color(self.text_color)
        
        # Labels
        self.ax1.set_ylabel('Temperature (°C)', color=self.temp_color, fontsize=12)
        self.ax2.set_ylabel('Pressure (hPa)', color=self.pressure_color, fontsize=12)
        self.ax2.set_xlabel('Time', color=self.text_color, fontsize=12)
        
        # Create empty plots for initialization
        self.temp_line, = self.ax1.plot([], [], lw=2, color=self.temp_color, label='Temperature')
        self.press_line, = self.ax2.plot([], [], lw=2, color=self.pressure_color, label='Pressure')
        
        # Add legends
        self.ax1.legend(loc='upper right', facecolor=self.bg_color, edgecolor=self.text_color)
        self.ax2.legend(loc='upper right', facecolor=self.bg_color, edgecolor=self.text_color)
        
        # Display the plot in Tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, master=graph_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add toolbar
        from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk
        self.toolbar = NavigationToolbar2Tk(self.canvas, graph_frame)
        self.toolbar.config(background=self.bg_color)
        self.toolbar._message_label.config(background=self.bg_color, foreground=self.text_color)
        for button in self.toolbar.winfo_children():
            if isinstance(button, tk.Button):
                button.config(background=self.bg_color, foreground=self.text_color, activebackground=self.accent_color)
        self.toolbar.update()
        self.toolbar.pack(fill=tk.X)
        
    def create_data_table(self, parent):
        """Create the data table display"""
        table_frame = ttk.LabelFrame(parent, text="Live Data Feed", padding=10)
        table_frame.pack(fill=tk.X, padx=20, pady=10)
        
        # Create treeview with scrollbar
        columns = ("timestamp", "time", "temperature", "pressure", "temp_delta", "press_delta", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=6)
        
        # Configure scrollbars
        y_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        x_scrollbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)
        
        y_scrollbar.pack(side="right", fill="y")
        x_scrollbar.pack(side="bottom", fill="x")
        
        # Configure columns
        self.tree.heading("timestamp", text="TIMESTAMP")
        self.tree.heading("time", text="ELAPSED TIME (s)")
        self.tree.heading("temperature", text="TEMPERATURE (°C)")
        self.tree.heading("pressure", text="PRESSURE (hPa)")
        self.tree.heading("temp_delta", text="TEMP CHANGE")
        self.tree.heading("press_delta", text="PRESS CHANGE")
        self.tree.heading("status", text="STATUS")
        
        self.tree.column("timestamp", anchor="center", width=180)
        self.tree.column("time", anchor="center", width=120)
        self.tree.column("temperature", anchor="center", width=150)
        self.tree.column("pressure", anchor="center", width=150)
        self.tree.column("temp_delta", anchor="center", width=120)
        self.tree.column("press_delta", anchor="center", width=120)
        self.tree.column("status", anchor="center", width=120)
        
        self.tree.pack(fill="both", expand=True)
        
        # Add table controls
        table_controls = ttk.Frame(table_frame)
        table_controls.pack(fill=tk.X, pady=(5, 0))
        
        # Clear table button
        clear_btn = ttk.Button(table_controls, text="Clear Table", command=self.clear_table)
        clear_btn.pack(side=tk.LEFT, padx=5)
        
        # Auto-scroll toggle
        self.auto_scroll_var = tk.BooleanVar(value=True)
        auto_scroll_check = ttk.Checkbutton(table_controls, text="Auto-scroll", variable=self.auto_scroll_var)
        auto_scroll_check.pack(side=tk.LEFT, padx=15)
        
        # Search in table
        ttk.Label(table_controls, text="Search:", style="Stats.TLabel").pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(table_controls, textvariable=self.search_var, width=20)
        search_entry.pack(side=tk.LEFT, padx=5)
        self.search_var.trace("w", self.search_table)
        
    def create_status_bar(self):
        """Create status bar at the bottom"""
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, padx=20, pady=(0, 10))
        
        self.status_var = tk.StringVar(value="Ready. Connect to serial port and press Start to begin recording.")
        status_label = ttk.Label(status_frame, textvariable=self.status_var, style="Stats.TLabel")
        status_label.pack(side=tk.LEFT, padx=5)
        
        # Version info and about button
        version_label = ttk.Label(status_frame, text="v2.0.0", style="Stats.TLabel")
        version_label.pack(side=tk.RIGHT, padx=5)
        
        about_btn = ttk.Button(status_frame, text="About", command=self.show_about)
        about_btn.pack(side=tk.RIGHT, padx=5)
        
        # Log view button
        log_btn = ttk.Button(status_frame, text="Error Log", command=self.show_error_log)
        log_btn.pack(side=tk.RIGHT, padx=5)
        
    def create_advanced_stats_panel(self, parent):
        """Create advanced statistics panel for the analysis tab"""
        # Main stats container
        stats_container = ttk.Frame(parent)
        stats_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Split into left and right sections
        left_stats = ttk.Frame(stats_container)
        left_stats.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        right_stats = ttk.Frame(stats_container)
        right_stats.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        
        # Basic Statistics Section
        basic_stats = ttk.LabelFrame(left_stats, text="Statistical Summary")
        basic_stats.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Create a text widget for statistics display
        self.stats_text = tk.Text(basic_stats, height=10, bg=self.bg_color, fg=self.text_color,
                                 font=("Consolas", 11), wrap=tk.WORD)
        self.stats_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.stats_text.config(state=tk.DISABLED)
        
        # Trend Analysis Section
        trend_stats = ttk.LabelFrame(left_stats, text="Trend Analysis")
        trend_stats.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.trend_text = tk.Text(trend_stats, height=8, bg=self.bg_color, fg=self.text_color,
                                font=("Consolas", 11), wrap=tk.WORD)
        self.trend_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.trend_text.config(state=tk.DISABLED)
        
        # Correlation Analysis
        corr_stats = ttk.LabelFrame(right_stats, text="Correlation Analysis")
        corr_stats.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Canvas for correlation chart
        self.corr_fig = plt.figure(figsize=(5, 4), facecolor=self.bg_color)
        self.corr_ax = self.corr_fig.add_subplot(111)
        self.corr_canvas = FigureCanvasTkAgg(self.corr_fig, master=corr_stats)
        self.corr_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Outlier Analysis
        outlier_stats = ttk.LabelFrame(right_stats, text="Outlier Detection")
        outlier_stats.pack(fill=tk.BOTH, expand=True, pady=10)
        
        outlier_controls = ttk.Frame(outlier_stats)
        outlier_controls.pack(fill=tk.X, padx=10, pady=5)
        
        self.outlier_enable_var = tk.BooleanVar(value=self.outlier_detection_enabled)
        outlier_check = ttk.Checkbutton(outlier_controls, text="Enable Outlier Detection", 
                                      variable=self.outlier_enable_var, command=self.toggle_outlier_detection)
        outlier_check.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(outlier_controls, text="Threshold (σ):", style="Stats.TLabel").pack(side=tk.LEFT, padx=10)
        
        self.outlier_threshold_var = tk.StringVar(value=str(self.outlier_threshold))
        threshold_combo = ttk.Combobox(outlier_controls, textvariable=self.outlier_threshold_var, width=5, state="readonly")
        threshold_combo.pack(side=tk.LEFT, padx=5)
        threshold_combo['values'] = ('1.5', '2.0', '2.5', '3.0', '3.5')
        threshold_combo.bind("<<ComboboxSelected>>", self.update_outlier_threshold)
        
        # List of detected outliers
        ttk.Label(outlier_stats, text="Detected Outliers:", style="Stats.TLabel").pack(anchor="w", padx=10, pady=5)
        
        self.outlier_list = tk.Listbox(outlier_stats, bg=self.bg_color, fg=self.text_color, height=6,
                                     font=("Consolas", 10))
        self.outlier_list.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
    def create_advanced_visualization(self, parent):
        """Create advanced visualization section for the analysis tab"""
        viz_frame = ttk.LabelFrame(parent, text="Advanced Visualization")
        viz_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Visualization controls
        controls_frame = ttk.Frame(viz_frame)
        controls_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Chart type selector
        ttk.Label(controls_frame, text="Chart Type:", style="Stats.TLabel").pack(side=tk.LEFT, padx=5)
        
        self.chart_type_var = tk.StringVar(value="distribution")
        chart_type_combo = ttk.Combobox(controls_frame, textvariable=self.chart_type_var, width=15, state="readonly")
        chart_type_combo.pack(side=tk.LEFT, padx=5)
        chart_type_combo['values'] = ('distribution', 'scatter', 'rate_of_change', 'forecast', 'boxplot')
        chart_type_combo.bind("<<ComboboxSelected>>", self.update_advanced_chart)
        
        # Data selector
        ttk.Label(controls_frame, text="Data:", style="Stats.TLabel").pack(side=tk.LEFT, padx=15)
        
        self.chart_data_var = tk.StringVar(value="both")
        chart_data_combo = ttk.Combobox(controls_frame, textvariable=self.chart_data_var, width=15, state="readonly")
        chart_data_combo.pack(side=tk.LEFT, padx=5)
        chart_data_combo['values'] = ('temperature', 'pressure', 'both')
        chart_data_combo.bind("<<ComboboxSelected>>", self.update_advanced_chart)
        
        # Time range selector
        ttk.Label(controls_frame, text="Time Range:", style="Stats.TLabel").pack(side=tk.LEFT, padx=15)
        
        self.chart_range_var = tk.StringVar(value="all")
        chart_range_combo = ttk.Combobox(controls_frame, textvariable=self.chart_range_var, width=10, state="readonly")
        chart_range_combo.pack(side=tk.LEFT, padx=5)
        chart_range_combo['values'] = ('all', 'last_30', 'last_60', 'last_5min', 'last_10min')
        chart_range_combo.bind("<<ComboboxSelected>>", self.update_advanced_chart)
        
        # Update chart button
        update_chart_btn = ttk.Button(controls_frame, text="Update Chart", command=self.update_advanced_chart)
        update_chart_btn.pack(side=tk.LEFT, padx=15)
        
        # Chart area
        self.adv_fig = plt.figure(figsize=(10, 6), facecolor=self.bg_color)
        self.adv_ax = self.adv_fig.add_subplot(111)
        self.adv_canvas = FigureCanvasTkAgg(self.adv_fig, master=viz_frame)
        self.adv_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Initialize with empty chart
        self.adv_ax.set_facecolor(self.bg_color)
        self.adv_ax.tick_params(colors=self.text_color)
        self.adv_ax.set_title("No Data Available", color=self.text_color)
        self.adv_fig.tight_layout()
        self.adv_canvas.draw()
    
    def create_connection_settings(self, parent):
        """Create connection settings panel"""
        conn_frame = ttk.LabelFrame(parent, text="Connection Settings", padding=10)
        conn_frame.pack(fill=tk.X, pady=10)
        
        # Baud rate
        baud_frame = ttk.Frame(conn_frame)
        baud_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(baud_frame, text="Baud Rate:", style="Stats.TLabel").pack(side=tk.LEFT, padx=5)
        
        self.baud_var = tk.StringVar(value=str(self.baud_rate))
        baud_combo = ttk.Combobox(baud_frame, textvariable=self.baud_var, width=10, state="readonly")
        baud_combo.pack(side=tk.LEFT, padx=5)
        baud_combo['values'] = ('9600', '19200', '38400', '57600', '115200')
        
        # Data format
        ttk.Label(baud_frame, text="Data Format:", style="Stats.TLabel").pack(side=tk.LEFT, padx=15)
        
        self.format_var = tk.StringVar(value="csv")
        format_combo = ttk.Combobox(baud_frame, textvariable=self.format_var, width=10, state="readonly")
        format_combo.pack(side=tk.LEFT, padx=5)
        format_combo['values'] = ('csv', 'json')
        
        # Auto-reconnect
        reconnect_frame = ttk.Frame(conn_frame)
        reconnect_frame.pack(fill=tk.X, pady=5)
        
        self.auto_reconnect_var = tk.BooleanVar(value=self.auto_reconnect)
        reconnect_check = ttk.Checkbutton(reconnect_frame, text="Auto-reconnect on connection loss", 
                                        variable=self.auto_reconnect_var, command=self.toggle_auto_reconnect)
        reconnect_check.pack(side=tk.LEFT, padx=5)
        
        # Max reconnect attempts
        ttk.Label(reconnect_frame, text="Max Attempts:", style="Stats.TLabel").pack(side=tk.LEFT, padx=15)
        
        self.max_attempts_var = tk.StringVar(value=str(self.max_reconnect_attempts))
        attempts_spin = ttk.Spinbox(reconnect_frame, from_=1, to=10, width=5, textvariable=self.max_attempts_var)
        attempts_spin.pack(side=tk.LEFT, padx=5)
        
        # Connection timeout
        timeout_frame = ttk.Frame(conn_frame)
        timeout_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(timeout_frame, text="Connection Timeout (s):", style="Stats.TLabel").pack(side=tk.LEFT, padx=5)
        
        self.timeout_var = tk.StringVar(value="2")
        timeout_spin = ttk.Spinbox(timeout_frame, from_=1, to=10, width=5, textvariable=self.timeout_var)
        timeout_spin.pack(side=tk.LEFT, padx=5)
        
        # Apply settings button
        apply_btn = ttk.Button(conn_frame, text="Apply Connection Settings", command=self.apply_connection_settings)
        apply_btn.pack(pady=10)
    
    def create_data_settings(self, parent):
        """Create data processing settings panel"""
        data_frame = ttk.LabelFrame(parent, text="Data Processing Settings", padding=10)
        data_frame.pack(fill=tk.X, pady=10)
        
        # Sample rate
        sample_frame = ttk.Frame(data_frame)
        sample_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(sample_frame, text="Target Sample Rate (samples/min):", style="Stats.TLabel").pack(side=tk.LEFT, padx=5)
        
        self.sample_rate_var = tk.StringVar(value="60")
        rate_spin = ttk.Spinbox(sample_frame, from_=1, to=300, width=5, textvariable=self.sample_rate_var)
        rate_spin.pack(side=tk.LEFT, padx=5)
        
        # Data filtering
        filter_frame = ttk.Frame(data_frame)
        filter_frame.pack(fill=tk.X, pady=5)
        
        self.filter_enable_var = tk.BooleanVar(value=True)
        filter_check = ttk.Checkbutton(filter_frame, text="Enable data filtering", 
                                     variable=self.filter_enable_var)
        filter_check.pack(side=tk.LEFT, padx=5)
        
        # Filter method
        ttk.Label(filter_frame, text="Filter Method:", style="Stats.TLabel").pack(side=tk.LEFT, padx=15)
        
        self.filter_method_var = tk.StringVar(value="moving_avg")
        filter_combo = ttk.Combobox(filter_frame, textvariable=self.filter_method_var, width=15, state="readonly")
        filter_combo.pack(side=tk.LEFT, padx=5)
        filter_combo['values'] = ('moving_avg', 'exponential', 'median', 'kalman')
        
        # Window size
        window_frame = ttk.Frame(data_frame)
        window_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(window_frame, text="Filter Window Size:", style="Stats.TLabel").pack(side=tk.LEFT, padx=5)
        
        self.window_size_var = tk.StringVar(value="5")
        window_spin = ttk.Spinbox(window_frame, from_=3, to=15, increment=2, width=5, textvariable=self.window_size_var)
        window_spin.pack(side=tk.LEFT, padx=5)
        
        # Valid ranges
        range_frame = ttk.Frame(data_frame)
        range_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(range_frame, text="Valid Temperature Range (°C):", style="Stats.TLabel").pack(side=tk.LEFT, padx=5)
        
        self.temp_min_var = tk.StringVar(value="-10")
        temp_min_spin = ttk.Spinbox(range_frame, from_=-50, to=50, width=5, textvariable=self.temp_min_var)
        temp_min_spin.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(range_frame, text="to", style="Stats.TLabel").pack(side=tk.LEFT)
        
        self.temp_max_var = tk.StringVar(value="60")
        temp_max_spin = ttk.Spinbox(range_frame, from_=0, to=100, width=5, textvariable=self.temp_max_var)
        temp_max_spin.pack(side=tk.LEFT, padx=5)
        
        # Pressure range
        press_range_frame = ttk.Frame(data_frame)
        press_range_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(press_range_frame, text="Valid Pressure Range (hPa):", style="Stats.TLabel").pack(side=tk.LEFT, padx=5)
        
        self.press_min_var = tk.StringVar(value="800")
        press_min_spin = ttk.Spinbox(press_range_frame, from_=700, to=1100, width=5, textvariable=self.press_min_var)
        press_min_spin.pack(side=tk.LEFT, padx=5)
        
        ttk.Label(press_range_frame, text="to", style="Stats.TLabel").pack(side=tk.LEFT)
        
        self.press_max_var = tk.StringVar(value="1100")
        press_max_spin = ttk.Spinbox(press_range_frame, from_=900, to=1200, width=5, textvariable=self.press_max_var)
        press_max_spin.pack(side=tk.LEFT, padx=5)
        
        # Apply settings button
        apply_data_btn = ttk.Button(data_frame, text="Apply Data Settings", command=self.apply_data_settings)
        apply_data_btn.pack(pady=10)
        
    def create_display_settings(self, parent):
        """Create display settings panel"""
        display_frame = ttk.LabelFrame(parent, text="Display Settings", padding=10)
        display_frame.pack(fill=tk.X, pady=10)
        
        # Chart refresh rate
        refresh_frame = ttk.Frame(display_frame)
        refresh_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(refresh_frame, text="Chart Refresh Rate (ms):", style="Stats.TLabel").pack(side=tk.LEFT, padx=5)
        
        self.refresh_var = tk.StringVar(value="1000")
        refresh_combo = ttk.Combobox(refresh_frame, textvariable=self.refresh_var, width=10, state="readonly")
        refresh_combo.pack(side=tk.LEFT, padx=5)
        refresh_combo['values'] = ('500', '1000', '2000', '5000')
        
        # Color theme
        theme_frame = ttk.Frame(display_frame)
        theme_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(theme_frame, text="Color Theme:", style="Stats.TLabel").pack(side=tk.LEFT, padx=5)
        
        self.theme_var = tk.StringVar(value="dark")
        theme_combo = ttk.Combobox(theme_frame, textvariable=self.theme_var, width=10, state="readonly")
        theme_combo.pack(side=tk.LEFT, padx=5)
        theme_combo['values'] = ('dark', 'light', 'blue', 'green')
        theme_combo.bind("<<ComboboxSelected>>", self.update_theme)
        
        # Table display options
        table_frame = ttk.Frame(display_frame)
        table_frame.pack(fill=tk.X, pady=5)
        
        self.show_delta_var = tk.BooleanVar(value=True)
        delta_check = ttk.Checkbutton(table_frame, text="Show rate of change columns", 
                                     variable=self.show_delta_var, command=self.update_table_columns)
        delta_check.pack(side=tk.LEFT, padx=5)
        
        # Max table rows
        ttk.Label(table_frame, text="Max Table Rows:", style="Stats.TLabel").pack(side=tk.LEFT, padx=15)
        
        self.max_rows_var = tk.StringVar(value="100")
        rows_combo = ttk.Combobox(table_frame, textvariable=self.max_rows_var, width=5, state="readonly")
        rows_combo.pack(side=tk.LEFT, padx=5)
        rows_combo['values'] = ('50', '100', '200', '500', '1000')
        
        # Apply display settings
        apply_display_btn = ttk.Button(display_frame, text="Apply Display Settings", command=self.apply_display_settings)
        apply_display_btn.pack(pady=10)
        
    def create_app_settings(self, parent):
        """Create application settings panel"""
        app_frame = ttk.LabelFrame(parent, text="Application Settings", padding=10)
        app_frame.pack(fill=tk.X, pady=10)
        
        # Auto-backup settings
        backup_frame = ttk.Frame(app_frame)
        backup_frame.pack(fill=tk.X, pady=5)
        
        self.auto_backup_var = tk.BooleanVar(value=True)
        backup_check = ttk.Checkbutton(backup_frame, text="Enable auto-backup of data", 
                                      variable=self.auto_backup_var)
        backup_check.pack(side=tk.LEFT, padx=5)
        
        # Backup interval
        ttk.Label(backup_frame, text="Backup Interval (min):", style="Stats.TLabel").pack(side=tk.LEFT, padx=15)
        
        self.backup_interval_var = tk.StringVar(value=str(self.backup_interval // 60))
        backup_spin = ttk.Spinbox(backup_frame, from_=1, to=30, width=5, textvariable=self.backup_interval_var)
        backup_spin.pack(side=tk.LEFT, padx=5)
        
        # Backup location
        backup_loc_frame = ttk.Frame(app_frame)
        backup_loc_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(backup_loc_frame, text="Backup Location:", style="Stats.TLabel").pack(side=tk.LEFT, padx=5)
        
        self.backup_dir_var = tk.StringVar(value="./backups")
        backup_entry = ttk.Entry(backup_loc_frame, textvariable=self.backup_dir_var, width=30)
        backup_entry.pack(side=tk.LEFT, padx=5)
        
        browse_btn = ttk.Button(backup_loc_frame, text="Browse...", command=self.browse_backup_dir)
        browse_btn.pack(side=tk.LEFT, padx=5)
        
        # Apply and save settings
        btn_frame = ttk.Frame(app_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        save_settings_btn = ttk.Button(btn_frame, text="Save All Settings", command=self.save_config)
        save_settings_btn.pack(side=tk.LEFT, padx=5)
        
        load_settings_btn = ttk.Button(btn_frame, text="Load Settings", command=self.load_config)
        load_settings_btn.pack(side=tk.LEFT, padx=5)
        
        reset_settings_btn = ttk.Button(btn_frame, text="Reset to Defaults", command=self.reset_to_defaults)
        reset_settings_btn.pack(side=tk.LEFT, padx=5)
        
    def refresh_ports(self):
        """Refresh the list of available COM ports"""
        try:
            ports = [port.device for port in serial.tools.list_ports.comports()]
            if not ports:
                ports = ["COM1", "COM2", "COM3", "COM4", "COM5"]  # Default options if none found
                self.status_var.set("No serial ports detected. Check connections and drivers.")
            else:
                self.status_var.set(f"Found {len(ports)} serial ports.")
            
            self.port_dropdown['values'] = ports
            
            if self.serial_port in ports:
                self.port_var.set(self.serial_port)
            elif ports:
                self.port_var.set(ports[0])
                self.serial_port = ports[0]
            
        except Exception as e:
            self.log_error(f"Error refreshing ports: {str(e)}")
            self.status_var.set("Error detecting serial ports.")
    
    def test_connection(self):
        """Test the serial port connection"""
        port = self.port_var.get()
        if not port:
            messagebox.showwarning("Connection Test", "Please select a COM port first.")
            return
            
        baud_rate = int(self.baud_var.get())
        
        try:
            # Attempt to open the port
            test_ser = serial.Serial(port, baud_rate, timeout=1)
            
            if test_ser.is_open:
                messagebox.showinfo("Connection Test", f"Successfully connected to {port} at {baud_rate} baud!")
                self.status_var.set(f"Connection test successful on {port}.")
                test_ser.close()
                
                # Update connection indicator
                self.connection_indicator.itemconfig("indicator", fill=self.success_color)
                self.connection_status.config(text=f"Port {port} available")
            
        except Exception as e:
            messagebox.showerror("Connection Test", f"Failed to connect to {port}:\n{str(e)}")
            self.status_var.set(f"Connection test failed: {str(e)}")
            
            # Update connection indicator
            self.connection_indicator.itemconfig("indicator", fill=self.highlight_color)
            self.connection_status.config(text="Disconnected")
            
    def start_recording(self):
        """Start recording data from serial port"""
        try:
            # Get COM port from dropdown
            self.serial_port = self.port_var.get()
            if not self.serial_port:
                messagebox.showwarning("Start Recording", "Please select a COM port first.")
                return
                
            # Get baud rate
            self.baud_rate = int(self.baud_var.get())
            
            # Attempt to open serial connection
            self.ser = serial.Serial(self.serial_port, self.baud_rate, timeout=1)
            
            # Reset data if not paused
            if not self.is_paused:
                self.temperature_data = []
                self.pressure_data = []
                self.time_stamps = []
                self.datetime_stamps = []
                self.temp_delta = []
                self.press_delta = []
                self.time_counter = 0
                
                # Clear existing table data
                self.clear_table()
                
                # Reset outlier list
                self.outlier_list.delete(0, tk.END)
                
            # Update state
            self.is_recording = True
            self.is_paused = False
            self.connection_active = True
            self.start_time = datetime.now() if not self.start_time else self.start_time
            
            # Update UI
            self.start_btn.config(state=tk.DISABLED)
            self.pause_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.NORMAL)
            self.status_var.set(f"Recording started on port {self.serial_port} at {self.baud_rate} baud...")
            self.update_connection_status(True, f"Connected to {self.serial_port}")
            
            # Start data collection in a separate thread
            self.collection_thread = threading.Thread(target=self.collect_data, daemon=True)
            self.collection_thread.start()
            
            # Start duration timer
            self.update_duration()
            
            # Setup watchdog
            self.setup_watchdog()
            
        except Exception as e:
            self.log_error(f"Start recording error: {str(e)}")
            messagebox.showerror("Connection Error", f"Could not open port {self.serial_port}:\n{str(e)}")
            self.status_var.set(f"Connection error: {str(e)}")
            self.update_connection_status(False, "Connection error")
    
    def pause_recording(self):
        """Pause recording but keep connection open"""
        if self.is_recording:
            self.is_paused = True
            self.is_recording = False
            
            # Update UI
            self.start_btn.config(state=tk.NORMAL)
            self.pause_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.status_var.set("Recording paused. Press Start to resume or Stop to end recording.")
            
            # Update connection status
            self.update_connection_status(True, f"Connected to {self.serial_port} (paused)")
    
    def stop_recording(self):
        """Stop recording data"""
        if self.is_recording or self.is_paused:
            self.is_recording = False
            self.is_paused = False
            
            # Close serial connection if open
            if self.ser and self.ser.is_open:
                try:
                    self.ser.close()
                except:
                    pass
                
            # Cancel watchdog timer if active
            if self.watchdog_timer:
                self.root.after_cancel(self.watchdog_timer)
                self.watchdog_timer = None
                
            # Update UI
            self.start_btn.config(state=tk.NORMAL)
            self.pause_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.DISABLED)
            self.status_var.set(f"Recording stopped. Collected {len(self.time_stamps)} data points.")
            self.update_connection_status(False, "Disconnected")
            self.connection_active = False
            
            # Reset start time and counter for new recording
            self.start_time = None
            
            # If data was collected, ask if user wants to save it
            if len(self.time_stamps) > 0:
                if messagebox.askyesno("Save Data", "Would you like to save the recorded data?"):
                    self.export_data("excel")
    
    def update_duration(self):
        """Update the recording duration display"""
        if not self.is_recording and not self.is_paused:
            return
            
        if self.start_time:
            elapsed = datetime.now() - self.start_time
            hours, remainder = divmod(elapsed.total_seconds(), 3600)
            minutes, seconds = divmod(remainder, 60)
            self.duration_var.set(f"Duration: {int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}")
            
            # Update sample rate if we have data
            if len(self.time_stamps) > 1 and elapsed.total_seconds() > 0:
                rate = len(self.time_stamps) / (elapsed.total_seconds() / 60)
                self.sample_count_var.set(f"Samples: {len(self.time_stamps)} | Rate: {rate:.1f} samples/min")
            
        # Schedule next update
        self.root.after(1000, self.update_duration)
    
    def collect_data(self):
        """Collect data from serial port - runs in a separate thread"""
        error_count = 0
        max_errors = 5
        data_format = self.format_var.get()  # csv or json
        
        while self.is_recording:
            try:
                if self.ser and self.ser.is_open and self.ser.in_waiting > 0:
                    # Read data from serial port
                    line = self.ser.readline().decode("utf-8").strip()
                    
                    # Parse data based on format
                    temperature, pressure = None, None
                    if data_format == "csv":
                        # Expect format: "temperature,pressure"
                        try:
                            parts = line.split(",")
                            if len(parts) >= 2:
                                temperature = float(parts[0])
                                pressure = float(parts[1])
                        except ValueError:
                            # Log but continue
                            self.log_error(f"Data parsing error: '{line}'")
                            continue
                    elif data_format == "json":
                        # Expect format: {"temp": value, "press": value}
                        try:
                            data = json.loads(line)
                            temperature = float(data.get("temp", 0))
                            pressure = float(data.get("press", 0))
                        except json.JSONDecodeError:
                            self.log_error(f"JSON parsing error: '{line}'")
                            continue
                    
                    # Validate data
                    if self.validate_data(temperature, pressure):
                        # Get current timestamp
                        current_time = datetime.now()
                        self.last_data_time = current_time
                        
                        # Calculate rate of change if not first data point
                        temp_change = 0
                        press_change = 0
                        if self.temperature_data:
                            temp_change = temperature - self.temperature_data[-1]
                            press_change = pressure - self.pressure_data[-1]
                        
                        # Store data
                        self.temperature_data.append(temperature)
                        self.pressure_data.append(pressure)
                        self.time_stamps.append(self.time_counter)
                        self.datetime_stamps.append(current_time)
                        self.temp_delta.append(temp_change)
                        self.press_delta.append(press_change)
                        
                        # Check for outliers
                        is_outlier = False
                        if self.outlier_detection_enabled and len(self.temperature_data) > 5:
                            is_outlier = self.check_for_outliers(temperature, pressure, self.time_counter)
                        
                        # Update UI in main thread
                        self.root.after(0, self.update_ui, temperature, pressure, current_time, 
                                      temp_change, press_change, is_outlier)
                        
                        # Increment time counter
                        self.time_counter += 1
                        
                        # Perform data backup if needed
                        current_seconds = time.time()
                        if (current_seconds - self.last_backup_time) > self.backup_interval and self.auto_backup_var.get():
                            self.backup_data()
                            self.last_backup_time = current_seconds
                        
                        # Reset error count on successful read
                        error_count = 0
                    
                    # Short delay between reads to prevent CPU hogging
                    time.sleep(0.05)
                    
                else:
                    # No data available, short delay
                    time.sleep(0.1)
                    
            except serial.SerialException as e:
                error_count += 1
                error_msg = f"Serial communication error: {str(e)}"
                self.root.after(0, lambda: self.status_var.set(error_msg))
                self.log_error(error_msg)
                
                # Handle connection loss
                if error_count >= max_errors:
                    if self.auto_reconnect and self.reconnect_attempts < self.max_reconnect_attempts:
                        self.reconnect_attempts += 1
                        self.root.after(0, lambda: self.status_var.set(f"Connection lost. Attempting to reconnect ({self.reconnect_attempts}/{self.max_reconnect_attempts})..."))
                        self.root.after(0, self.update_connection_status, False, "Reconnecting...")
                        
                        # Close existing connection
                        try:
                            if self.ser and self.ser.is_open:
                                self.ser.close()
                        except:
                            pass
                            
                        # Try to reconnect
                        try:
                            time.sleep(2)  # Wait before reconnect
                            self.ser = serial.Serial(self.serial_port, self.baud_rate, timeout=1)
                            if self.ser.is_open:
                                error_count = 0
                                self.root.after(0, lambda: self.status_var.set(f"Reconnected to {self.serial_port}"))
                                self.root.after(0, self.update_connection_status, True, f"Connected to {self.serial_port}")
                                self.reconnect_attempts = 0
                        except:
                            pass
                    else:
                        # Stop recording if max attempts reached
                        self.root.after(0, lambda: self.status_var.set("Connection lost. Max reconnect attempts reached."))
                        self.root.after(0, self.update_connection_status, False, "Disconnected")
                        self.root.after(0, self.stop_recording)
                        break
                
                time.sleep(1)  # Delay before retry
                
            except Exception as e:
                error_msg = f"Error reading data: {str(e)}"
                self.root.after(0, lambda: self.status_var.set(error_msg))
                self.log_error(error_msg)
                time.sleep(1)  # Wait before retrying
    
    def validate_data(self, temperature, pressure):
        """Validate that data is within acceptable ranges"""
        if temperature is None or pressure is None:
            return False
            
        # Get validity ranges from settings
        try:
            temp_min = float(self.temp_min_var.get())
            temp_max = float(self.temp_max_var.get())
            press_min = float(self.press_min_var.get())
            press_max = float(self.press_max_var.get())
            
            # Check against ranges
            valid_temp = temp_min <= temperature <= temp_max
            valid_press = press_min <= pressure <= press_max
            
            return valid_temp and valid_press
            
        except ValueError:
            # Default ranges if settings not valid
            return -50 <= temperature <= 100 and 700 <= pressure <= 1200
    
    def check_for_outliers(self, temperature, pressure, timestamp):
        """Check if new data point is an outlier using Z-score"""
        is_outlier = False
        threshold = float(self.outlier_threshold_var.get())
        
        # Need enough data for meaningful statistics
        if len(self.temperature_data) < 5:
            return False
        
        # Calculate z-scores
        temp_array = np.array(self.temperature_data[:-1])  # Exclude the new point
        press_array = np.array(self.pressure_data[:-1])  # Exclude the new point
        
        temp_mean = np.mean(temp_array)
        temp_std = np.std(temp_array)
        press_mean = np.mean(press_array)
        press_std = np.std(press_array)
        
        # Avoid division by zero
        if temp_std > 0:
            temp_z = abs((temperature - temp_mean) / temp_std)
            if temp_z > threshold:
                is_outlier = True
                outlier_msg = f"Temperature outlier at t={timestamp}: {temperature:.2f}°C (z={temp_z:.2f})"
                self.root.after(0, lambda: self.outlier_list.insert(0, outlier_msg))
                self.log_error(outlier_msg)
        
        if press_std > 0:
            press_z = abs((pressure - press_mean) / press_std)
            if press_z > threshold:
                is_outlier = True
                outlier_msg = f"Pressure outlier at t={timestamp}: {pressure:.2f}hPa (z={press_z:.2f})"
                self.root.after(0, lambda: self.outlier_list.insert(0, outlier_msg))
                self.log_error(outlier_msg)
        
        # Limit outlier list size
        if self.outlier_list.size() > 20:
            self.outlier_list.delete(20, tk.END)
            
        return is_outlier
    
    def update_ui(self, temperature, pressure, timestamp, temp_change, press_change, is_outlier):
        """Update UI elements with new data"""
        try:
            # Add to table (newest at the top)
            formatted_time = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            status = "OUTLIER" if is_outlier else "OK"
            
            # Prepare delta values with appropriate sign
            temp_delta_str = f"{temp_change:+.2f}" if temp_change != 0 else "0.00"
            press_delta_str = f"{press_change:+.2f}" if press_change != 0 else "0.00"
            
            # Add to table
            self.tree.insert("", 0, values=(
                formatted_time, 
                self.time_counter, 
                f"{temperature:.2f}", 
                f"{pressure:.2f}",
                temp_delta_str,
                press_delta_str,
                status
            ))
            
            # Highlight row if outlier
            if is_outlier:
                item_id = self.tree.get_children()[0]
                self.tree.item(item_id, tags=("outlier",))
                self.tree.tag_configure("outlier", background=self.highlight_color, foreground=self.bg_color)
            
            # Keep table size manageable
            max_rows = int(self.max_rows_var.get())
            if len(self.tree.get_children()) > max_rows:
                # Remove oldest entries (at the bottom)
                old_items = self.tree.get_children()[-(max_rows // 10):]
                for item in old_items:
                    self.tree.delete(item)
            
            # Auto-scroll if enabled
            if self.auto_scroll_var.get() and self.tree.get_children():
                self.tree.see(self.tree.get_children()[0])
            
            # Update basic stats
            if self.temperature_data:
                temp_min = min(self.temperature_data)
                temp_max = max(self.temperature_data)
                temp_avg = sum(self.temperature_data) / len(self.temperature_data)
                self.temp_stats_var.set(f"Min: {temp_min:.2f}°C | Max: {temp_max:.2f}°C | Avg: {temp_avg:.2f}°C")
                
                # Current and rate of change (per minute)
                self.temp_current_var.set(f"Current: {temperature:.2f}°C | Change: {self.calculate_rate_of_change(self.temperature_data):.2f}°C/min")
                
            if self.pressure_data:
                press_min = min(self.pressure_data)
                press_max = max(self.pressure_data)
                press_avg = sum(self.pressure_data) / len(self.pressure_data)
                self.press_stats_var.set(f"Min: {press_min:.2f}hPa | Max: {press_max:.2f}hPa | Avg: {press_avg:.2f}hPa")
                
                # Current and rate of change
                self.press_current_var.set(f"Current: {pressure:.2f}hPa | Change: {self.calculate_rate_of_change(self.pressure_data):.2f}hPa/min")
            
            # Update alert status
            self.update_alert_status()
            
            # Update graphs
            self.update_plots()
            
            # Update advanced statistics if that tab is selected
            if self.tab_control.index(self.tab_control.select()) == 1:  # Analysis tab
                self.update_statistics()
                self.update_correlation()
            
        except Exception as e:
            error_msg = f"Error updating UI: {str(e)}"
            self.status_var.set(error_msg)
            self.log_error(error_msg)
    
    def calculate_rate_of_change(self, data_list, window=10):
        """Calculate rate of change per minute over recent data points"""
        if len(data_list) < 2 or len(self.datetime_stamps) < 2:
            return 0.0
            
        # Use only recent data points
        samples = min(window, len(data_list))
        recent_data = data_list[-samples:]
        recent_times = self.datetime_stamps[-samples:]
        
        # Calculate time difference in minutes
        time_diff = (recent_times[-1] - recent_times[0]).total_seconds() / 60.0
        if time_diff <= 0:
            return 0.0
            
        # Calculate value difference
        value_diff = recent_data[-1] - recent_data[0]
        
        # Return rate of change per minute
        return value_diff / time_diff
    
    def update_alert_status(self):
        """Update alert status based on current data"""
        if not self.temperature_data or not self.pressure_data:
            return
            
        alerts = []
        
        # Check for rapid temperature changes
        temp_rate = self.calculate_rate_of_change(self.temperature_data)
        if abs(temp_rate) > 5:  # More than 5°C per minute
            alerts.append(f"Rapid temperature change: {temp_rate:.1f}°C/min")
            
        # Check for rapid pressure changes (potential weather events)
        press_rate = self.calculate_rate_of_change(self.pressure_data)
        if abs(press_rate) > 1:  # More than 1hPa per minute
            alerts.append(f"Rapid pressure change: {press_rate:.1f}hPa/min")
            
        # Check for extreme values
        current_temp = self.temperature_data[-1]
        current_press = self.pressure_data[-1]
        
        if current_temp > 50:
            alerts.append(f"High temperature: {current_temp:.1f}°C")
        elif current_temp < 0:
            alerts.append(f"Low temperature: {current_temp:.1f}°C")
            
        if current_press < 950:
            alerts.append(f"Low pressure: {current_press:.1f}hPa")
        elif current_press > 1050:
            alerts.append(f"High pressure: {current_press:.1f}hPa")
            
        # Update the UI with alerts
        if alerts:
            alert_text = " | ".join(alerts)
            self.alert_var.set(alert_text)
            self.alert_label.configure(style="Alert.TLabel")
        else:
            self.alert_var.set("No alerts")
            self.alert_label.configure(style="Stats.TLabel")
    
    def update_plots(self):
        """Update the plots with the latest data"""
        if not self.time_stamps:
            return
            
        # Clear axes
        self.ax1.clear()
        self.ax2.clear()
        
        # Reconfiguring axes
        for ax in [self.ax1, self.ax2]:
            ax.tick_params(colors=self.text_color)
            ax.grid(True, alpha=0.3)
            ax.set_facecolor(self.bg_color)
            for spine in ax.spines.values():
                spine.set_color(self.text_color)
        
        # Get plot style
        plot_style = self.plot_type_var.get()
        
        # Plot data based on style
        if plot_style == 'line' or plot_style == 'both':
            self.ax1.plot(self.time_stamps, self.temperature_data, color=self.temp_color,
                         linestyle='-', linewidth=2, label='Temperature')
            self.ax2.plot(self.time_stamps, self.pressure_data, color=self.pressure_color,
                         linestyle='-', linewidth=2, label='Pressure')
                         
        if plot_style == 'scatter' or plot_style == 'both':
            self.ax1.scatter(self.time_stamps, self.temperature_data, color=self.temp_color, 
                           marker='o', s=30, alpha=0.7, label='Temperature' if plot_style == 'scatter' else None)
            self.ax2.scatter(self.time_stamps, self.pressure_data, color=self.pressure_color,
                           marker='o', s=30, alpha=0.7, label='Pressure' if plot_style == 'scatter' else None)
        
        # Add data point labels if enabled
        if self.data_labels_var.get() and len(self.time_stamps) <= 30:
            for i, (t, temp, press) in enumerate(zip(self.time_stamps, self.temperature_data, self.pressure_data)):
                # Only label every nth point if there are many
                if i % max(1, len(self.time_stamps) // 10) == 0:
                    self.ax1.annotate(f"{temp:.1f}", (t, temp), textcoords="offset points", 
                                    xytext=(0, 5), ha='center', fontsize=8, color=self.temp_color)
                    self.ax2.annotate(f"{press:.1f}", (t, press), textcoords="offset points", 
                                    xytext=(0, 5), ha='center', fontsize=8, color=self.pressure_color)
        
        # Set limits based on time window
        time_window = self.time_window_var.get()
        if len(self.time_stamps) > 1:
            if time_window != 'all':
                window_size = int(time_window)
                if len(self.time_stamps) > window_size:
                    start_index = max(0, len(self.time_stamps) - window_size)
                    visible_times = self.time_stamps[start_index:]
                    visible_temps = self.temperature_data[start_index:]
                    visible_press = self.pressure_data[start_index:]
                else:
                    visible_times = self.time_stamps
                    visible_temps = self.temperature_data
                    visible_press = self.pressure_data
                    
                # Set x limits
                self.ax1.set_xlim(visible_times[0], visible_times[-1] + 2)
                
                # Set y limits with padding
                temp_min, temp_max = min(visible_temps), max(visible_temps)
                press_min, press_max = min(visible_press), max(visible_press)
                
                temp_range = max(0.5, temp_max - temp_min)
                press_range = max(0.5, press_max - press_min)
                
                self.ax1.set_ylim(temp_min - 0.1*temp_range, temp_max + 0.1*temp_range)
                self.ax2.set_ylim(press_min - 0.1*press_range, press_max + 0.1*press_range)
            else:
                # Show all data
                self.ax1.set_xlim(0, self.time_stamps[-1] + 2)
                
                # Add padding to y-axis
                temp_min, temp_max = min(self.temperature_data), max(self.temperature_data)
                press_min, press_max = min(self.pressure_data), max(self.pressure_data)
                
                temp_range = max(0.5, temp_max - temp_min)
                press_range = max(0.5, press_max - press_min)
                
                self.ax1.set_ylim(temp_min - 0.1*temp_range, temp_max + 0.1*temp_range)
                self.ax2.set_ylim(press_min - 0.1*press_range, press_max + 0.1*press_range)
            
            # Use MaxNLocator to get nice tick values
            self.ax1.yaxis.set_major_locator(MaxNLocator(nbins=5, prune='both'))
            self.ax2.yaxis.set_major_locator(MaxNLocator(nbins=5, prune='both'))
        
        # Restore labels
        self.ax1.set_ylabel('Temperature (°C)', color=self.temp_color, fontsize=12)
        self.ax2.set_ylabel('Pressure (hPa)', color=self.pressure_color, fontsize=12)
        self.ax2.set_xlabel('Time (s)', color=self.text_color, fontsize=12)
        
        # Add statistics overlay if enabled
        if self.stat_overlay_var.get() and len(self.temperature_data) > 1:
            # Temperature stats
            temp_stats = (
                f"Min: {min(self.temperature_data):.1f}°C\n"
                f"Max: {max(self.temperature_data):.1f}°C\n"
                f"Avg: {sum(self.temperature_data)/len(self.temperature_data):.1f}°C\n"
                f"Δ: {self.calculate_rate_of_change(self.temperature_data):.1f}°C/min"
            )
            self.ax1.text(0.02, 0.98, temp_stats, transform=self.ax1.transAxes, fontsize=9,
                        verticalalignment='top', horizontalalignment='left',
                        bbox=dict(boxstyle='round', facecolor=self.bg_color, alpha=0.8, edgecolor=self.temp_color))
            
            # Pressure stats
            press_stats = (
                f"Min: {min(self.pressure_data):.1f}hPa\n"
                f"Max: {max(self.pressure_data):.1f}hPa\n"
                f"Avg: {sum(self.pressure_data)/len(self.pressure_data):.1f}hPa\n"
                f"Δ: {self.calculate_rate_of_change(self.pressure_data):.1f}hPa/min"
            )
            self.ax2.text(0.02, 0.98, press_stats, transform=self.ax2.transAxes, fontsize=9,
                        verticalalignment='top', horizontalalignment='left',
                        bbox=dict(boxstyle='round', facecolor=self.bg_color, alpha=0.8, edgecolor=self.pressure_color))
        
        # Add legends
        self.ax1.legend(loc='upper right', facecolor=self.bg_color, edgecolor=self.text_color)
        self.ax2.legend(loc='upper right', facecolor=self.bg_color, edgecolor=self.text_color)
        
        # Update canvas
        self.fig.tight_layout()
        self.canvas.draw()
    
    def update_statistics(self):
        """Update statistical information in the analysis tab"""
        if not self.temperature_data or len(self.temperature_data) < 2:
            self.stats_text.config(state=tk.NORMAL)
            self.stats_text.delete(1.0, tk.END)
            self.stats_text.insert(tk.END, "Not enough data for statistical analysis.")
            self.stats_text.config(state=tk.DISABLED)
            return
            
        try:
            # Calculate statistics
            temp_array = np.array(self.temperature_data)
            press_array = np.array(self.pressure_data)
            
            # Basic statistics
            temp_stats = {
                'Min': np.min(temp_array),
                'Max': np.max(temp_array),
                'Mean': np.mean(temp_array),
                'Median': np.median(temp_array),
                'Std Dev': np.std(temp_array),
                'Variance': np.var(temp_array),
                'Range': np.ptp(temp_array),
                'IQR': np.percentile(temp_array, 75) - np.percentile(temp_array, 25),
                '25th %': np.percentile(temp_array, 25),
                '75th %': np.percentile(temp_array, 75),
                'Skewness': stats.skew(temp_array) if len(temp_array) > 8 else 'N/A',
                'Kurtosis': stats.kurtosis(temp_array) if len(temp_array) > 8 else 'N/A',
            }
            
            press_stats = {
                'Min': np.min(press_array),
                'Max': np.max(press_array),
                'Mean': np.mean(press_array),
                'Median': np.median(press_array),
                'Std Dev': np.std(press_array),
                'Variance': np.var(press_array),
                'Range': np.ptp(press_array),
                'IQR': np.percentile(press_array, 75) - np.percentile(press_array, 25),
                '25th %': np.percentile(press_array, 25),
                '75th %': np.percentile(press_array, 75),
                'Skewness': stats.skew(press_array) if len(press_array) > 8 else 'N/A',
                'Kurtosis': stats.kurtosis(press_array) if len(press_array) > 8 else 'N/A',
            }
            
            # Create formatted text output
            stat_text = "STATISTICAL SUMMARY\n\n"
            stat_text += "Temperature (°C):\n"
            for key, value in temp_stats.items():
                if isinstance(value, (int, float)):
                    stat_text += f"{key}: {value:.4f}\n"
                else:
                    stat_text += f"{key}: {value}\n"
            
            stat_text += "\nPressure (hPa):\n"
            for key, value in press_stats.items():
                if isinstance(value, (int, float)):
                    stat_text += f"{key}: {value:.4f}\n"
                else:
                    stat_text += f"{key}: {value}\n"
            
            # Update the text widget
            self.stats_text.config(state=tk.NORMAL)
            self.stats_text.delete(1.0, tk.END)
            self.stats_text.insert(tk.END, stat_text)
            self.stats_text.config(state=tk.DISABLED)
            
            # Update trend analysis
            self.update_trend_analysis()
            
        except Exception as e:
            self.log_error(f"Error updating statistics: {str(e)}")
            self.stats_text.config(state=tk.NORMAL)
            self.stats_text.delete(1.0, tk.END)
            self.stats_text.insert(tk.END, f"Error calculating statistics: {str(e)}")
            self.stats_text.config(state=tk.DISABLED)
    
    def update_trend_analysis(self):
        """Perform trend analysis on the collected data"""
        if len(self.temperature_data) < 10:
            self.trend_text.config(state=tk.NORMAL)
            self.trend_text.delete(1.0, tk.END)
            self.trend_text.insert(tk.END, "Need at least 10 data points for trend analysis.")
            self.trend_text.config(state=tk.DISABLED)
            return
            
        try:
            # Simple linear regression for temperature
            x = np.array(self.time_stamps)
            y_temp = np.array(self.temperature_data)
            y_press = np.array(self.pressure_data)
            
            # Calculate temperature trend
            temp_slope, temp_intercept, temp_r, temp_p, temp_stderr = stats.linregress(x, y_temp)
            temp_trend_str = f"Temperature Trend: {temp_slope:.6f}°C/s"
            if abs(temp_slope) < 0.001:
                temp_trend_str += " (stable)"
            elif temp_slope > 0:
                temp_trend_str += " (increasing)"
            else:
                temp_trend_str += " (decreasing)"
            
            # Calculate pressure trend
            press_slope, press_intercept, press_r, press_p, press_stderr = stats.linregress(x, y_press)
            press_trend_str = f"Pressure Trend: {press_slope:.6f}hPa/s"
            if abs(press_slope) < 0.001:
                press_trend_str += " (stable)"
            elif press_slope > 0:
                press_trend_str += " (increasing)"
            else:
                press_trend_str += " (decreasing)"
            
            # Forecast
            if len(x) > 10:
                last_time = x[-1]
                forecast_time = last_time + self.forecast_horizon
                
                temp_forecast = temp_slope * forecast_time + temp_intercept
                press_forecast = press_slope * forecast_time + press_intercept
                
                # Calculate confidence values
                temp_conf = temp_stderr * 1.96  # 95% confidence
                press_conf = press_stderr * 1.96  # 95% confidence
                
                temp_forecast_str = f"Temperature Forecast ({self.forecast_horizon}s ahead): "
                temp_forecast_str += f"{temp_forecast:.2f}°C ± {temp_conf:.2f}"
                
                press_forecast_str = f"Pressure Forecast ({self.forecast_horizon}s ahead): "
                press_forecast_str += f"{press_forecast:.2f}hPa ± {press_conf:.2f}"
            else:
                temp_forecast_str = "Temperature Forecast: Insufficient data"
                press_forecast_str = "Pressure Forecast: Insufficient data"
            
            # Correlation between temperature and pressure
            if len(y_temp) == len(y_press):
                corr, p_value = stats.pearsonr(y_temp, y_press)
                if abs(p_value) < 0.05:
                    sig_str = "statistically significant"
                else:
                    sig_str = "not statistically significant"
                    
                corr_str = f"Temp-Press Correlation: {corr:.4f} ({sig_str}, p={p_value:.4f})"
            else:
                corr_str = "Temp-Press Correlation: Data length mismatch"
            
                        # Create the trend analysis text
            trend_text = "TREND ANALYSIS\n\n"
            trend_text += f"{temp_trend_str}\n"
            trend_text += f"{press_trend_str}\n\n"
            trend_text += f"{temp_forecast_str}\n"
            trend_text += f"{press_forecast_str}\n\n"
            trend_text += f"{corr_str}\n"
            
            # Add weather interpretation if available
            if len(self.pressure_data) > 30:
                last_30_pressure = self.pressure_data[-30:]
                pressure_change = last_30_pressure[-1] - last_30_pressure[0]
                
                if pressure_change < -3:
                    weather_str = "Weather Indication: Rapid pressure drop may indicate approaching storm."
                elif pressure_change < -1:
                    weather_str = "Weather Indication: Pressure dropping, weather may deteriorate."
                elif pressure_change > 3:
                    weather_str = "Weather Indication: Rapid pressure rise, clear weather likely."
                elif pressure_change > 1:
                    weather_str = "Weather Indication: Pressure rising, weather may improve."
                else:
                    weather_str = "Weather Indication: Pressure stable, no significant changes expected."
                
                trend_text += f"\n{weather_str}\n"
            
            # Update the text widget
            self.trend_text.config(state=tk.NORMAL)
            self.trend_text.delete(1.0, tk.END)
            self.trend_text.insert(tk.END, trend_text)
            self.trend_text.config(state=tk.DISABLED)
            
        except Exception as e:
            self.log_error(f"Error updating trend analysis: {str(e)}")
            self.trend_text.config(state=tk.NORMAL)
            self.trend_text.delete(1.0, tk.END)
            self.trend_text.insert(tk.END, f"Error analyzing trends: {str(e)}")
            self.trend_text.config(state=tk.DISABLED)
    
    def update_correlation(self):
        """Update the correlation analysis chart"""
        if len(self.temperature_data) < 5 or len(self.pressure_data) < 5:
            self.corr_ax.clear()
            self.corr_ax.set_facecolor(self.bg_color)
            self.corr_ax.text(0.5, 0.5, "Not enough data for correlation analysis", 
                           horizontalalignment='center', verticalalignment='center',
                           transform=self.corr_ax.transAxes, color=self.text_color)
            self.corr_fig.tight_layout()
            self.corr_canvas.draw()
            return
        
        try:
            # Clear the axis
            self.corr_ax.clear()
            self.corr_ax.set_facecolor(self.bg_color)
            self.corr_ax.tick_params(colors=self.text_color)
            
            for spine in self.corr_ax.spines.values():
                spine.set_color(self.text_color)
            
            # Create scatter plot of temperature vs pressure
            scatter = self.corr_ax.scatter(self.temperature_data, self.pressure_data, 
                                        alpha=0.7, c=self.time_stamps, cmap='viridis', s=30)
            
            # Add color bar to show time progression
            cbar = self.corr_fig.colorbar(scatter, ax=self.corr_ax)
            cbar.set_label('Time (s)', color=self.text_color)
            cbar.ax.yaxis.set_tick_params(color=self.text_color)
            cbar.outline.set_edgecolor(self.text_color)
            plt.setp(plt.getp(cbar.ax, 'yticklabels'), color=self.text_color)
            
            # Calculate and plot best fit line if sufficient data
            if len(self.temperature_data) > 2:
                slope, intercept, r_value, p_value, std_err = stats.linregress(
                    self.temperature_data, self.pressure_data)
                
                x_range = np.linspace(min(self.temperature_data), max(self.temperature_data), 100)
                self.corr_ax.plot(x_range, intercept + slope * x_range, color=self.secondary_accent, 
                               linestyle='--', linewidth=2)
                
                # Add correlation coefficient to plot
                corr_text = f"r = {r_value:.4f}\np = {p_value:.4f}"
                self.corr_ax.text(0.05, 0.95, corr_text, transform=self.corr_ax.transAxes,
                              color=self.text_color, fontsize=10, verticalalignment='top',
                              bbox=dict(boxstyle='round', facecolor=self.bg_color, alpha=0.7, 
                                      edgecolor=self.text_color))
            
            # Set labels
            self.corr_ax.set_xlabel('Temperature (°C)', color=self.text_color)
            self.corr_ax.set_ylabel('Pressure (hPa)', color=self.text_color)
            self.corr_ax.set_title('Temperature vs Pressure Correlation', color=self.text_color)
            
            # Update the canvas
            self.corr_fig.tight_layout()
            self.corr_canvas.draw()
            
        except Exception as e:
            self.log_error(f"Error updating correlation plot: {str(e)}")
            self.corr_ax.clear()
            self.corr_ax.set_facecolor(self.bg_color)
            self.corr_ax.text(0.5, 0.5, f"Error: {str(e)}", 
                           horizontalalignment='center', verticalalignment='center',
                           transform=self.corr_ax.transAxes, color=self.highlight_color)
            self.corr_fig.tight_layout()
            self.corr_canvas.draw()
    
    def update_advanced_chart(self, event=None):
        """Update the advanced visualization chart"""
        if not self.temperature_data or len(self.temperature_data) < 2:
            self.adv_ax.clear()
            self.adv_ax.set_facecolor(self.bg_color)
            self.adv_ax.text(0.5, 0.5, "Not enough data for advanced visualization", 
                          horizontalalignment='center', verticalalignment='center',
                          transform=self.adv_ax.transAxes, color=self.text_color)
            self.adv_fig.tight_layout()
            self.adv_canvas.draw()
            return
            
        try:
            # Get chart settings
            chart_type = self.chart_type_var.get()
            data_type = self.chart_data_var.get()
            time_range = self.chart_range_var.get()
            
            # Filter data by time range
            if time_range == 'all':
                temp_data = np.array(self.temperature_data)
                press_data = np.array(self.pressure_data)
                time_data = np.array(self.time_stamps)
                temp_delta_data = np.array(self.temp_delta)
                press_delta_data = np.array(self.press_delta)
            else:
                # Parse time range
                if time_range == 'last_30':
                    n_points = 30
                elif time_range == 'last_60':
                    n_points = 60
                elif time_range == 'last_5min':
                    n_points = 5 * 60
                elif time_range == 'last_10min':
                    n_points = 10 * 60
                else:
                    n_points = min(30, len(self.temperature_data))
                    
                # Get the last n points or all if less than n
                n_points = min(n_points, len(self.temperature_data))
                temp_data = np.array(self.temperature_data[-n_points:])
                press_data = np.array(self.pressure_data[-n_points:])
                time_data = np.array(self.time_stamps[-n_points:])
                temp_delta_data = np.array(self.temp_delta[-n_points:])
                press_delta_data = np.array(self.press_delta[-n_points:])
            
            # Clear the current plot
            self.adv_ax.clear()
            self.adv_ax.set_facecolor(self.bg_color)
            self.adv_ax.tick_params(colors=self.text_color)
            
            for spine in self.adv_ax.spines.values():
                spine.set_color(self.text_color)
            
            # Create the requested chart type
            if chart_type == 'distribution':
                # Create histogram for distribution
                if data_type == 'temperature' or data_type == 'both':
                    self.adv_ax.hist(temp_data, bins=min(20, len(temp_data)//3 + 1), alpha=0.7, 
                                   color=self.temp_color, label='Temperature')
                    
                if data_type == 'pressure' or data_type == 'both':
                    self.adv_ax.hist(press_data, bins=min(20, len(press_data)//3 + 1), alpha=0.5, 
                                   color=self.pressure_color, label='Pressure')
                    
                self.adv_ax.set_xlabel('Value', color=self.text_color)
                self.adv_ax.set_ylabel('Frequency', color=self.text_color)
                self.adv_ax.set_title('Data Distribution', color=self.text_color)
                
            elif chart_type == 'scatter':
                # Create scatter plot showing time evolution
                if data_type == 'temperature':
                    scatter = self.adv_ax.scatter(time_data, temp_data, c=time_data, 
                                               cmap='autumn', alpha=0.8, s=40)
                    self.adv_ax.set_ylabel('Temperature (°C)', color=self.text_color)
                elif data_type == 'pressure':
                    scatter = self.adv_ax.scatter(time_data, press_data, c=time_data, 
                                               cmap='winter', alpha=0.8, s=40)
                    self.adv_ax.set_ylabel('Pressure (hPa)', color=self.text_color)
                else:  # both
                    fig, ax1 = plt.subplots()
                    ax1.set_xlabel('Time (s)')
                    ax1.set_ylabel('Temperature (°C)', color=self.temp_color)
                    ax1.plot(time_data, temp_data, color=self.temp_color)
                    ax1.tick_params(axis='y', labelcolor=self.temp_color)
                    
                    ax2 = ax1.twinx()
                    ax2.set_ylabel('Pressure (hPa)', color=self.pressure_color)
                    ax2.plot(time_data, press_data, color=self.pressure_color)
                    ax2.tick_params(axis='y', labelcolor=self.pressure_color)
                    
                    fig.tight_layout()
                    
                self.adv_ax.set_xlabel('Time (s)', color=self.text_color)
                self.adv_ax.set_title('Data Scatter Plot', color=self.text_color)
                
            elif chart_type == 'rate_of_change':
                # Create plot showing rate of change over time
                if data_type == 'temperature' or data_type == 'both':
                    self.adv_ax.plot(time_data[1:], temp_delta_data[1:], color=self.temp_color, 
                                   label='Temperature Change', alpha=0.8)
                    
                if data_type == 'pressure' or data_type == 'both':
                    self.adv_ax.plot(time_data[1:], press_delta_data[1:], color=self.pressure_color, 
                                   label='Pressure Change', alpha=0.8)
                    
                self.adv_ax.set_xlabel('Time (s)', color=self.text_color)
                self.adv_ax.set_ylabel('Rate of Change', color=self.text_color)
                self.adv_ax.set_title('Rate of Change Over Time', color=self.text_color)
                
            elif chart_type == 'forecast':
                # Create forecast chart with confidence intervals
                # For temperature
                if data_type == 'temperature' or data_type == 'both':
                    # Fit linear regression
                    slope, intercept, r_value, p_value, std_err = stats.linregress(time_data, temp_data)
                    
                    # Predict values
                    pred_x = np.append(time_data, np.arange(time_data[-1]+1, time_data[-1]+self.forecast_horizon+1))
                    pred_y = intercept + slope * pred_x
                    
                    # Plot actual data
                    self.adv_ax.plot(time_data, temp_data, 'o', color=self.temp_color, 
                                   label='Temperature Data', alpha=0.7, markersize=4)
                    
                    # Plot prediction line
                    self.adv_ax.plot(pred_x, pred_y, '--', color=self.temp_color, 
                                   label='Temperature Forecast', alpha=0.9)
                    
                    # Add confidence interval
                    conf_interval = 1.96 * std_err
                    self.adv_ax.fill_between(pred_x, pred_y - conf_interval, pred_y + conf_interval, 
                                          color=self.temp_color, alpha=0.2)
                
                # For pressure
                if data_type == 'pressure' or data_type == 'both':
                    # Fit linear regression
                    slope, intercept, r_value, p_value, std_err = stats.linregress(time_data, press_data)
                    
                    # Predict values
                    pred_x = np.append(time_data, np.arange(time_data[-1]+1, time_data[-1]+self.forecast_horizon+1))
                    pred_y = intercept + slope * pred_x
                    
                    # Plot actual data
                    self.adv_ax.plot(time_data, press_data, 'o', color=self.pressure_color, 
                                   label='Pressure Data', alpha=0.7, markersize=4)
                    
                    # Plot prediction line
                    self.adv_ax.plot(pred_x, pred_y, '--', color=self.pressure_color, 
                                   label='Pressure Forecast', alpha=0.9)
                    
                    # Add confidence interval
                    conf_interval = 1.96 * std_err
                    self.adv_ax.fill_between(pred_x, pred_y - conf_interval, pred_y + conf_interval, 
                                          color=self.pressure_color, alpha=0.2)
                
                self.adv_ax.set_xlabel('Time (s)', color=self.text_color)
                self.adv_ax.set_ylabel('Value', color=self.text_color)
                self.adv_ax.set_title('Data Forecast', color=self.text_color)
                
                # Add vertical line to separate historical data from forecast
                self.adv_ax.axvline(x=time_data[-1], color=self.text_color, linestyle=':', alpha=0.7)
                self.adv_ax.text(time_data[-1]+0.5, min(temp_data.min(), press_data.min()), 
                              'Forecast →', color=self.text_color, ha='left', va='bottom')
                
            elif chart_type == 'boxplot':
                # Create boxplot for data distribution
                box_data = []
                labels = []
                
                if data_type == 'temperature' or data_type == 'both':
                    box_data.append(temp_data)
                    labels.append('Temperature')
                    
                if data_type == 'pressure' or data_type == 'both':
                    box_data.append(press_data)
                    labels.append('Pressure')
                    
                boxplot = self.adv_ax.boxplot(box_data, patch_artist=True, labels=labels)
                
                # Set colors
                colors = [self.temp_color, self.pressure_color]
                for i, box in enumerate(boxplot['boxes']):
                    if i < len(colors):
                        box.set(facecolor=colors[i], alpha=0.6)
                    box.set(edgecolor=self.text_color)
                
                for element in ['whiskers', 'caps', 'medians']:
                    for item in boxplot[element]:
                        item.set(color=self.text_color)
                
                self.adv_ax.set_ylabel('Value', color=self.text_color)
                self.adv_ax.set_title('Data Distribution Boxplot', color=self.text_color)
            
            # Add legend if needed
            if (chart_type in ['distribution', 'rate_of_change', 'forecast'] and 
                (data_type == 'both' or 
                 (chart_type == 'forecast' and (data_type == 'temperature' or data_type == 'pressure')))):
                self.adv_ax.legend(facecolor=self.bg_color, edgecolor=self.text_color)
            
            # Update the canvas
            self.adv_fig.tight_layout()
            self.adv_canvas.draw()
            
        except Exception as e:
            self.log_error(f"Error updating advanced chart: {str(e)}")
            self.adv_ax.clear()
            self.adv_ax.set_facecolor(self.bg_color)
            self.adv_ax.text(0.5, 0.5, f"Error creating chart: {str(e)}", 
                          horizontalalignment='center', verticalalignment='center',
                          transform=self.adv_ax.transAxes, color=self.highlight_color)
            self.adv_fig.tight_layout()
            self.adv_canvas.draw()
    
    def export_data(self, format_type="excel"):
        """Export collected data to file"""
        if not self.time_stamps:
            messagebox.showinfo("Export Info", "No data available to export.")
            return
            
        try:
            # Format timestamps
            formatted_times = [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in self.datetime_stamps]
            
            # Create DataFrame
            df = pd.DataFrame({
                'Timestamp': formatted_times,
                'Elapsed Time (s)': self.time_stamps,
                'Temperature (°C)': self.temperature_data,
                'Pressure (hPa)': self.pressure_data,
                'Temperature Change': self.temp_delta,
                'Pressure Change': self.press_delta
            })
            
            # Let user choose save location
            current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if format_type == "excel":
                default_filename = f"sensor_data_{current_time}.xlsx"
                file_path = filedialog.asksaveasfilename(
                    defaultextension=".xlsx",
                    filetypes=[("Excel Files", "*.xlsx"), ("All Files", "*.*")],
                    initialfile=default_filename
                )
                
                if not file_path:
                    return  # User canceled
                    
                # Export to Excel with multiple sheets
                with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                    # Raw data sheet
                    df.to_excel(writer, sheet_name='Raw Data', index=False)
                    
                    # Statistics sheet
                    if len(self.temperature_data) > 0:
                        # Create stats dataframe
                        stats_data = {
                            'Metric': ['Minimum', 'Maximum', 'Average', 'Median', 'Standard Deviation', 
                                      'Variance', 'Range', 'IQR', 'Skewness', 'Kurtosis'],
                            'Temperature (°C)': [
                                min(self.temperature_data),
                                max(self.temperature_data),
                                sum(self.temperature_data) / len(self.temperature_data),
                                sorted(self.temperature_data)[len(self.temperature_data) // 2],
                                np.std(self.temperature_data),
                                np.var(self.temperature_data),
                                max(self.temperature_data) - min(self.temperature_data),
                                np.percentile(self.temperature_data, 75) - np.percentile(self.temperature_data, 25),
                                stats.skew(self.temperature_data) if len(self.temperature_data) > 8 else 'N/A',
                                stats.kurtosis(self.temperature_data) if len(self.temperature_data) > 8 else 'N/A'
                            ],
                            'Pressure (hPa)': [
                                min(self.pressure_data),
                                max(self.pressure_data),
                                sum(self.pressure_data) / len(self.pressure_data),
                                sorted(self.pressure_data)[len(self.pressure_data) // 2],
                                np.std(self.pressure_data),
                                np.var(self.pressure_data),
                                max(self.pressure_data) - min(self.pressure_data),
                                np.percentile(self.pressure_data, 75) - np.percentile(self.pressure_data, 25),
                                stats.skew(self.pressure_data) if len(self.pressure_data) > 8 else 'N/A',
                                stats.kurtosis(self.pressure_data) if len(self.pressure_data) > 8 else 'N/A'
                            ]
                        }
                        stats_df = pd.DataFrame(stats_data)
                        stats_df.to_excel(writer, sheet_name='Statistics', index=False)
                        
                        # Add session info sheet
                        session_info = {
                            'Metric': ['Start Time', 'End Time', 'Duration', 'Total Samples', 
                                     'Sample Rate', 'COM Port', 'Baud Rate'],
                            'Value': [
                                self.datetime_stamps[0].strftime("%Y-%m-%d %H:%M:%S") if self.datetime_stamps else 'N/A',
                                self.datetime_stamps[-1].strftime("%Y-%m-%d %H:%M:%S") if self.datetime_stamps else 'N/A',
                                str(timedelta(seconds=self.time_stamps[-1])) if self.time_stamps else 'N/A',
                                len(self.time_stamps),
                                f"{len(self.time_stamps) / (self.time_stamps[-1] / 60):.2f} samples/min" if self.time_stamps and self.time_stamps[-1] > 0 else 'N/A',
                                self.serial_port,
                                self.baud_rate
                            ]
                        }
                        session_df = pd.DataFrame(session_info)
                        session_df.to_excel(writer, sheet_name='Session Info', index=False)
                
            elif format_type == "csv":
                default_filename = f"sensor_data_{current_time}.csv"
                file_path = filedialog.asksaveasfilename(
                    defaultextension=".csv",
                    filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
                    initialfile=default_filename
                )
                
                if not file_path:
                    return  # User canceled
                    
                # Export to CSV
                df.to_csv(file_path, index=False)
                
            self.status_var.set(f"Data exported successfully to {os.path.basename(file_path)}")
            messagebox.showinfo("Export Successful", f"Data has been exported to {file_path}")
            
        except Exception as e:
            error_msg = f"Failed to export data: {str(e)}"
            self.log_error(error_msg)
            messagebox.showerror("Export Error", error_msg)
            self.status_var.set(error_msg)
    
    def backup_data(self):
        """Backup data to a local file"""
        if not self.temperature_data or not self.auto_backup_var.get():
            return
            
        try:
            # Ensure backup directory exists
            backup_dir = self.backup_dir_var.get()
            os.makedirs(backup_dir, exist_ok=True)
            
            # Create backup filename
            session_time = self.start_time.strftime("%Y%m%d_%H%M%S") if self.start_time else datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(backup_dir, f"backup_{session_time}.csv")
            
            # Format data
            data = []
            for i in range(len(self.time_stamps)):
                row = [
                    self.datetime_stamps[i].strftime("%Y-%m-%d %H:%M:%S") if i < len(self.datetime_stamps) else "",
                    self.time_stamps[i] if i < len(self.time_stamps) else "",
                    self.temperature_data[i] if i < len(self.temperature_data) else "",
                    self.pressure_data[i] if i < len(self.pressure_data) else "",
                    self.temp_delta[i] if i < len(self.temp_delta) else "",
                    self.press_delta[i] if i < len(self.press_delta) else ""
                ]
                data.append(row)
                
            # Write to CSV
            with open(backup_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Timestamp', 'Elapsed Time (s)', 'Temperature (°C)', 'Pressure (hPa)', 'Temp Change', 'Press Change'])
                writer.writerows(data)
                
            # Update status (but don't interrupt the user)
            self.status_var.set(f"Auto-backup completed: {os.path.basename(backup_file)}")
            
        except Exception as e:
            error_msg = f"Auto-backup failed: {str(e)}"
            self.log_error(error_msg)
            # Don't show error message to avoid interrupting the user
    
    def clear_table(self):
        """Clear the data table"""
        for item in self.tree.get_children():
            self.tree.delete(item)
    
    def search_table(self, *args):
        """Search within the data table"""
        search_term = self.search_var.get().lower()
        if not search_term:
            # Reset all item display
            for item in self.tree.get_children():
                self.tree.item(item, tags=self.tree.item(item)['tags'])
        else:
            # Search in all columns
            for item in self.tree.get_children():
                values = self.tree.item(item)['values']
                found = False
                
                if values:  # Check if values exists
                    for value in values:
                        if search_term in str(value).lower():
                            found = True
                            break
                
                if found:
                    # Highlight the matching items
                    self.tree.item(item, tags=('match',))
                else:
                    # Dim the non-matching items
                    self.tree.item(item, tags=('no_match',))
                    
            # Configure tags
            self.tree.tag_configure('match', background=self.accent_color, foreground=self.bg_color)
            self.tree.tag_configure('no_match', background=self.bg_color, foreground=self.text_color)
            
            # Expand all items to show matches
            for item in self.tree.get_children():
                self.tree.item(item, open=True)
    
    def update_connection_status(self, connected, status_text):
        """Update the connection status indicator"""
        if connected:
            self.connection_indicator.itemconfig("indicator", fill=self.success_color)
            self.connection_active = True
        else:
            self.connection_indicator.itemconfig("indicator", fill=self.highlight_color)
            self.connection_active = False
            
        self.connection_status.config(text=status_text)
    
    def setup_watchdog(self):
        """Set up a watchdog timer to monitor data flow"""
        # Cancel existing timer if any
        if self.watchdog_timer:
            self.root.after_cancel(self.watchdog_timer)
            
        if self.is_recording:
            # Check data flow
            self.check_data_flow()
            
            # Schedule next check
            self.watchdog_timer = self.root.after(5000, self.setup_watchdog)
    
    def check_data_flow(self):
        """Check if data is flowing correctly"""
        if not self.is_recording or not self.connection_active:
            return
            
        if self.last_data_time:
            time_since_last_data = (datetime.now() - self.last_data_time).total_seconds()
            
            # If no data for more than 5 seconds, show warning
            if time_since_last_data > 5:
                self.status_var.set(f"Warning: No data received for {time_since_last_data:.1f} seconds.")
                self.connection_indicator.itemconfig("indicator", fill=self.warning_color)
                
                # If no data for more than 10 seconds, consider connection lost
                if time_since_last_data > 10 and self.auto_reconnect:
                    self.status_var.set("Data flow interrupted. Attempting to reconnect...")
                    
                    # Try to reconnect in a separate thread to avoid freezing UI
                    threading.Thread(target=self.attempt_reconnect, daemon=True).start()
    
    def attempt_reconnect(self):
        """Attempt to reconnect to the serial port"""
        if not self.connection_active or not self.is_recording:
            return
            
        try:
            # Close existing connection
            if self.ser and self.ser.is_open:
                self.ser.close()
                
            # Short delay
            time.sleep(1)
            
            # Try to reconnect
            self.ser = serial.Serial(self.serial_port, self.baud_rate, timeout=1)
            
            if self.ser.is_open:
                self.root.after(0, lambda: self.status_var.set(f"Reconnected to {self.serial_port}"))
                self.root.after(0, lambda: self.update_connection_status(True, f"Connected to {self.serial_port}"))
            
        except Exception as e:
            error_msg = f"Reconnection failed: {str(e)}"
            self.log_error(error_msg)
            self.self.log_error(error_msg)
            self.root.after(0, lambda: self.status_var.set(error_msg))
    
    #-------------------------------------------
    # UI Event Handlers
    #-------------------------------------------
    
    def on_tab_changed(self, event):
        """Handle tab change events"""
        current_tab = self.tab_control.index(self.tab_control.select())
        
        # Update statistics if analysis tab selected
        if current_tab == 1 and len(self.temperature_data) > 1:  # Analysis tab
            self.update_statistics()
            self.update_correlation()
            self.update_advanced_chart()
    
    def toggle_outlier_detection(self):
        """Toggle outlier detection on/off"""
        self.outlier_detection_enabled = self.outlier_enable_var.get()
    
    def update_outlier_threshold(self, event=None):
        """Update the outlier detection threshold"""
        try:
            self.outlier_threshold = float(self.outlier_threshold_var.get())
        except ValueError:
            # Reset to default if invalid
            self.outlier_threshold_var.set("3.0")
            self.outlier_threshold = 3.0
    
    def update_time_window(self, event=None):
        """Update the plot time window"""
        try:
            window = self.time_window_var.get()
            if window != 'all':
                self.time_window = int(window)
            self.update_plots()
        except ValueError:
            # Reset to default
            self.time_window_var.set(str(self.time_window))
    
    def toggle_auto_reconnect(self):
        """Toggle auto-reconnect feature"""
        self.auto_reconnect = self.auto_reconnect_var.get()
    
    def update_table_columns(self):
        """Update which columns are displayed in the table"""
        # Remember selected item
        selected = self.tree.selection()
        
        # Get current state of delta column display
        show_delta = self.show_delta_var.get()
        
        # Save all data
        data = []
        for item in self.tree.get_children():
            data.append((item, self.tree.item(item, 'values'), self.tree.item(item, 'tags')))
            
        # Clear table
        self.clear_table()
        
        # Configure columns
        if show_delta:
            # Show all columns
            for col in self.tree['columns']:
                self.tree.column(col, stretch=True)
        else:
            # Hide delta columns
            self.tree.column('temp_delta', width=0, stretch=False)
            self.tree.column('press_delta', width=0, stretch=False)
            
        # Restore data
        for item_id, values, tags in data:
            new_id = self.tree.insert('', 'end', values=values, tags=tags)
            if item_id in selected:
                self.tree.selection_add(new_id)
    
    def update_theme(self, event=None):
        """Update color theme"""
        theme = self.theme_var.get()
        
        if theme == 'dark':
            self.bg_color = "#1E1E2E"
            self.accent_color = "#94E2D5"
            self.secondary_accent = "#F5C2E7"
            self.text_color = "#CDD6F4"
            self.temp_color = "#FAB387"
            self.pressure_color = "#89B4FA"
            self.highlight_color = "#F38BA8"
            self.success_color = "#A6E3A1"
            self.warning_color = "#F9E2AF"
        elif theme == 'light':
            self.bg_color = "#FFFFFF"
            self.accent_color = "#0078D7"
            self.secondary_accent = "#E81123"
            self.text_color = "#000000"
            self.temp_color = "#FF8C00"
            self.pressure_color = "#0078D7"
            self.highlight_color = "#E81123"
            self.success_color = "#107C10"
            self.warning_color = "#FFB900"
        elif theme == 'blue':
            self.bg_color = "#172030"
            self.accent_color = "#61AFEF"
            self.secondary_accent = "#C678DD"
            self.text_color = "#ABB2BF"
            self.temp_color = "#E06C75"
            self.pressure_color = "#56B6C2"
            self.highlight_color = "#E06C75"
            self.success_color = "#98C379"
            self.warning_color = "#E5C07B"
        elif theme == 'green':
            self.bg_color = "#282C34"
            self.accent_color = "#98C379"
            self.secondary_accent = "#E06C75"
            self.text_color = "#ABB2BF"
            self.temp_color = "#E5C07B"
            self.pressure_color = "#61AFEF"
            self.highlight_color = "#C678DD"
            self.success_color = "#98C379"
            self.warning_color = "#E5C07B"
            
        # Update styles
        self.configure_styles()
        
        # Redraw plots if data exists
        if self.temperature_data:
            self.update_plots()
            if self.tab_control.index(self.tab_control.select()) == 1:
                self.update_correlation()
                self.update_advanced_chart()
    
    def browse_backup_dir(self):
        """Browse for backup directory"""
        backup_dir = filedialog.askdirectory(title="Select Backup Directory")
        if backup_dir:
            self.backup_dir_var.set(backup_dir)
    
    #-------------------------------------------
    # Settings Management
    #-------------------------------------------
    
    def apply_connection_settings(self):
        """Apply connection settings"""
        try:
            # Update baud rate
            self.baud_rate = int(self.baud_var.get())
            
            # Update auto-reconnect settings
            self.auto_reconnect = self.auto_reconnect_var.get()
            self.max_reconnect_attempts = int(self.max_attempts_var.get())
            
            # If currently connected, ask about reconnecting
            if self.connection_active and self.is_recording:
                if messagebox.askyesno("Apply Settings", 
                                     "Applying settings requires reconnection. Do you want to reconnect now?"):
                    self.stop_recording()
                    self.start_recording()
                    
            messagebox.showinfo("Settings", "Connection settings applied successfully.")
            
        except Exception as e:
            error_msg = f"Error applying connection settings: {str(e)}"
            self.log_error(error_msg)
            messagebox.showerror("Settings Error", error_msg)
    
    def apply_data_settings(self):
        """Apply data processing settings"""
        try:
            # Update filter settings
            self.filter_enable = self.filter_enable_var.get()
            
            # Update valid data ranges
            temp_min = float(self.temp_min_var.get())
            temp_max = float(self.temp_max_var.get())
            press_min = float(self.press_min_var.get())
            press_max = float(self.press_max_var.get())
            
            # Validate ranges
            if temp_min >= temp_max:
                raise ValueError("Temperature minimum must be less than maximum")
                
            if press_min >= press_max:
                raise ValueError("Pressure minimum must be less than maximum")
            
            messagebox.showinfo("Settings", "Data processing settings applied successfully.")
            
        except Exception as e:
            error_msg = f"Error applying data settings: {str(e)}"
            self.log_error(error_msg)
            messagebox.showerror("Settings Error", error_msg)
    
    def apply_display_settings(self):
        """Apply display settings"""
        try:
            # Update table display
            self.update_table_columns()
            
            # Update max rows
            max_rows = int(self.max_rows_var.get())
            
            # Trim table if needed
            if len(self.tree.get_children()) > max_rows:
                excess = len(self.tree.get_children()) - max_rows
                old_items = self.tree.get_children()[-excess:]
                for item in old_items:
                    self.tree.delete(item)
            
            messagebox.showinfo("Settings", "Display settings applied successfully.")
            
        except Exception as e:
            error_msg = f"Error applying display settings: {str(e)}"
            self.log_error(error_msg)
            messagebox.showerror("Settings Error", error_msg)
    
    def load_config(self):
        """Load configuration from file"""
        try:
            if not os.path.exists(self.config_file):
                return
                
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                
            # Load connection settings
            if 'serial_port' in config:
                self.serial_port = config['serial_port']
                self.port_var.set(self.serial_port)
                
            if 'baud_rate' in config:
                self.baud_rate = config['baud_rate']
                self.baud_var.set(str(self.baud_rate))
                
            if 'auto_reconnect' in config:
                self.auto_reconnect = config['auto_reconnect']
                self.auto_reconnect_var.set(self.auto_reconnect)
                
            if 'max_reconnect_attempts' in config:
                self.max_reconnect_attempts = config['max_reconnect_attempts']
                self.max_attempts_var.set(str(self.max_reconnect_attempts))
                
            # Load data processing settings
            if 'outlier_detection_enabled' in config:
                self.outlier_detection_enabled = config['outlier_detection_enabled']
                self.outlier_enable_var.set(self.outlier_detection_enabled)
                
            if 'outlier_threshold' in config:
                self.outlier_threshold = config['outlier_threshold']
                self.outlier_threshold_var.set(str(self.outlier_threshold))
                
            # Load display settings
            if 'theme' in config:
                self.theme_var.set(config['theme'])
                self.update_theme()
                
            if 'plot_mode' in config:
                self.plot_type_var.set(config['plot_mode'])
                
            if 'time_window' in config:
                self.time_window = config['time_window']
                self.time_window_var.set(str(self.time_window))
                
            if 'show_statistics_overlay' in config:
                self.show_statistics_overlay = config['show_statistics_overlay']
                self.stat_overlay_var.set(self.show_statistics_overlay)
                
            if 'show_data_labels' in config:
                self.show_data_labels = config['show_data_labels']
                self.data_labels_var.set(self.show_data_labels)
                
            # Load backup settings
            if 'backup_interval' in config:
                self.backup_interval = config['backup_interval']
                self.backup_interval_var.set(str(self.backup_interval // 60))
                
            if 'backup_dir' in config:
                self.backup_dir_var.set(config['backup_dir'])
                
            # Update status
            self.status_var.set("Configuration loaded successfully.")
            
        except Exception as e:
            error_msg = f"Error loading configuration: {str(e)}"
            self.log_error(error_msg)
            self.status_var.set(error_msg)
    
    def save_config(self):
        """Save configuration to file"""
        try:
            config = {
                # Connection settings
                'serial_port': self.port_var.get(),
                'baud_rate': int(self.baud_var.get()),
                'auto_reconnect': self.auto_reconnect_var.get(),
                'max_reconnect_attempts': int(self.max_attempts_var.get()),
                
                # Data processing settings
                'outlier_detection_enabled': self.outlier_enable_var.get(),
                'outlier_threshold': float(self.outlier_threshold_var.get()),
                
                # Display settings
                'theme': self.theme_var.get(),
                'plot_mode': self.plot_type_var.get(),
                'time_window': self.time_window,
                'show_statistics_overlay': self.stat_overlay_var.get(),
                'show_data_labels': self.data_labels_var.get(),
                
                # Backup settings
                'backup_interval': int(self.backup_interval_var.get()) * 60,
                'backup_dir': self.backup_dir_var.get()
            }
            
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=4)
                
            messagebox.showinfo("Settings", "Configuration saved successfully.")
            self.status_var.set("Configuration saved successfully.")
            
        except Exception as e:
            error_msg = f"Error saving configuration: {str(e)}"
            self.log_error(error_msg)
            messagebox.showerror("Settings Error", error_msg)
    
    def reset_to_defaults(self):
        """Reset all settings to defaults"""
        if messagebox.askyesno("Reset Settings", "Are you sure you want to reset all settings to defaults?"):
            # Connection settings
            self.baud_rate = 9600
            self.baud_var.set("9600")
            self.auto_reconnect = True
            self.auto_reconnect_var.set(True)
            self.max_reconnect_attempts = 5
            self.max_attempts_var.set("5")
            self.format_var.set("csv")
            
            # Data processing settings
            self.outlier_detection_enabled = True
            self.outlier_enable_var.set(True)
            self.outlier_threshold = 3.0
            self.outlier_threshold_var.set("3.0")
            self.filter_enable_var.set(True)
            self.filter_method_var.set("moving_avg")
            self.window_size_var.set("5")
            self.temp_min_var.set("-10")
            self.temp_max_var.set("60")
            self.press_min_var.set("800")
            self.press_max_var.set("1100")
            
            # Display settings
            self.theme_var.set("dark")
            self.update_theme()
            self.plot_type_var.set("line")
            self.time_window = 60
            self.time_window_var.set("60")
            self.show_statistics_overlay = True
            self.stat_overlay_var.set(True)
            self.show_data_labels = False
            self.data_labels_var.set(False)
            self.show_delta_var.set(True)
            self.max_rows_var.set("100")
            
            # Backup settings
            self.backup_interval = 60
            self.backup_interval_var.set("1")
            self.auto_backup_var.set(True)
            self.backup_dir_var.set("./backups")
            
            # Refresh UI
            self.update_plots()
            if self.tab_control.index(self.tab_control.select()) == 1:
                self.update_correlation()
                self.update_advanced_chart()
                
            # Save to file
            try:
                if os.path.exists(self.config_file):
                    os.remove(self.config_file)
            except:
                pass
                
            messagebox.showinfo("Settings", "Settings reset to defaults successfully.")
            self.status_var.set("Settings reset to defaults.")
    
    #-------------------------------------------
    # Helper Functions
    #-------------------------------------------
    
    def log_error(self, message):
        """Log an error message with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.error_log.append(f"{timestamp}: {message}")
        
        # Limit log size
        if len(self.error_log) > 100:
            self.error_log = self.error_log[-100:]
    
    def show_error_log(self):
        """Display the error log"""
        if not self.error_log:
            messagebox.showinfo("Error Log", "No errors have been logged.")
            return
            
        # Create a dialog to display errors
        log_dialog = tk.Toplevel(self.root)
        log_dialog.title("Error Log")
        log_dialog.geometry("800x400")
        log_dialog.configure(bg=self.bg_color)
        
        # Add scrolled text widget
        log_text = tk.Text(log_dialog, bg=self.bg_color, fg=self.text_color, wrap=tk.WORD,
                         font=("Consolas", 10))
        scrollbar = ttk.Scrollbar(log_dialog, orient="vertical", command=log_text.yview)
        log_text.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Insert log entries
        for entry in self.error_log:
            log_text.insert(tk.END, entry + "\n")
            
        log_text.config(state=tk.DISABLED)
        
        # Add buttons
        button_frame = ttk.Frame(log_dialog)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Copy button
        copy_btn = ttk.Button(button_frame, text="Copy to Clipboard", 
                            command=lambda: self.copy_to_clipboard(log_text.get(1.0, tk.END)))
        copy_btn.pack(side=tk.LEFT, padx=5)
        
        # Clear button
        clear_btn = ttk.Button(button_frame, text="Clear Log", 
                             command=lambda: [self.error_log.clear(), log_dialog.destroy()])
        clear_btn.pack(side=tk.LEFT, padx=5)
        
        # Close button
        close_btn = ttk.Button(button_frame, text="Close", command=log_dialog.destroy)
        close_btn.pack(side=tk.RIGHT, padx=5)
        
        # Make dialog modal
        log_dialog.transient(self.root)
        log_dialog.grab_set()
        self.root.wait_window(log_dialog)
    
    def copy_to_clipboard(self, text):
        """Copy text to clipboard"""
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set("Copied to clipboard.")
    
    def show_about(self):
        """Show about dialog"""
        about_text = """Temperature & Pressure Monitoring System
Version 2.0.0

A professional data acquisition and analysis tool for temperature and pressure sensors.

Features:
• Real-time data monitoring and visualization
• Advanced statistical analysis
• Multiple visualization options
• Data export and backup capabilities
• Robust error handling and connection management

© 2025 Engineering Solutions
"""
        
        messagebox.showinfo("About", about_text)
    
    def on_closing(self):
        """Handle window closing event"""
        if self.is_recording:
            if not messagebox.askyesno("Exit", "Recording is in progress. Are you sure you want to exit?"):
                return
            
            # Stop recording
            self.stop_recording()
            
        # Save settings
        try:
            self.save_config()
        except:
            pass
            
        # Close the window
        self.root.destroy()

# Main execution
if __name__ == "__main__":
    try:
        # Set up app
        root = tk.Tk()
        app = TemperaturePressureLogger(root)
        
        # Run the application
        root.mainloop()
        
    except Exception as e:
        # Handle any uncaught exceptions
        error_message = f"Critical Application Error: {str(e)}\n\n{traceback.format_exc()}"
        print(error_message)
        
        # If GUI is available, show error dialog
        try:
            messagebox.showerror("Critical Error", error_message)
        except:
            pass