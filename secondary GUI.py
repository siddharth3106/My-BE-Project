import serial
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib as mpl
from datetime import datetime
import time
import os
import threading

class CurrentMonitoringSystem:
    def __init__(self, root):  # Fixed: Changed _init_ to __init__
        # Configuration
        self.serial_port = 'COM5'
        self.baud_rate = 9600
        self.ser = None
        self.available_ports = []
        
        # App state
        self.is_recording = False
        self.time_counter = 0
        self.start_time = None
        self.data_interval = 1.0  # seconds
        self.auto_scaling = True
        
        # Data storage - multiple current channels
        self.current_data = [[] for _ in range(6)]  # I1 to I6
        self.time_stamps = []
        self.datetime_stamps = []
        self.total_charge = [0.0, 0.0, 0.0]  # Q1, Q2, Q3
        self.max_data_points = 10000  # Limit storage to prevent memory issues
        
        # Color scheme
        self.bg_color = "#F0F0F0"  # Light background
        self.line_colors = ['#0000FF', '#FF8C00', '#008000', '#8B008B', '#FF0000', '#00BFFF']  # For I1-I6
        
        # Setup the root window
        self.root = root
        
        # Initialize UI elements
        self.port_var = None
        self.baud_var = None
        self.sync_var = None
        self.channel_var = None
        self.status_var = None
        self.current_tree = None
        self.charge_tree = None
        self.start_btn = None
        self.stop_btn = None
        self.plot_settings_window = None
        
        # Setup UI
        self.setup_ui()
        self.scan_serial_ports()
        
    # All other methods remain the same...
    def setup_ui(self):
        """Setup the user interface"""
        self.root.title("VEDANTRIK TECHNOLOGIES - RCPT")
        self.root.geometry("1200x800")
        self.root.configure(bg=self.bg_color)
        self.root.minsize(1000, 700)
        
        # Set up the menu bar
        self.create_menu_bar()
        
        # Configure the ttk style
        self.configure_styles()
        
        # Main frame with border
        main_frame = ttk.Frame(self.root, style="Main.TFrame")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Header with company name and logo
        self.create_header(main_frame)
        
        # Create left panel with Communication and Current Details
        left_panel = ttk.Frame(main_frame, style="Panel.TFrame")
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Create right panel with Connection and Plot
        right_panel = ttk.Frame(main_frame, style="Panel.TFrame")
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Communication Manager
        self.create_communication_manager(left_panel)
        
        # Current Details
        self.create_current_details(left_panel)
        
        # Total Charge Penetrated
        self.create_total_charge(left_panel)
        
        # Connection Manager
        self.create_connection_manager(right_panel)
        
        # Plot
        self.create_plot_panel(right_panel)
        
        # Status bar
        self.create_status_bar(main_frame)
        
        # Create a popup for plot settings
        self.create_plot_settings_dialog()
        
    def configure_styles(self):
        """Configure ttk styles for widgets"""
        self.style = ttk.Style()
        
        # Configure colors and fonts for widgets
        self.style.configure("Main.TFrame", relief="groove", borderwidth=2)
        self.style.configure("Panel.TFrame", relief="groove", borderwidth=1)
        self.style.configure("Title.TLabel", font=("Arial", 14, "bold"))
        self.style.configure("Header.TLabel", font=("Arial", 12, "bold"))
        self.style.configure("Normal.TLabel", font=("Arial", 10))
        
        # Button styles
        self.style.configure("TButton", font=("Arial", 10))
        
    def create_header(self, parent):
        """Create the header with company name and logo"""
        header_frame = ttk.Frame(parent, style="Panel.TFrame")
        header_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Left - Logo placeholder
        logo_frame = ttk.Frame(header_frame, width=100, height=50, style="Panel.TFrame")
        logo_frame.pack(side=tk.LEFT, padx=5, pady=5)
        logo_label = ttk.Label(logo_frame, text="LOGO", style="Title.TLabel")
        logo_label.pack(expand=True)
        
        # Center - Company name
        company_label = ttk.Label(header_frame, text="VEDANTRIK TECHNOLOGIES", style="Title.TLabel")
        company_label.pack(side=tk.LEFT, expand=True, padx=5, pady=5)
        
        # Right - Product name
        product_label = ttk.Label(header_frame, text="RCPT", style="Title.TLabel")
        product_label.pack(side=tk.RIGHT, padx=5, pady=5)
        
    def create_menu_bar(self):
        """Create the application menu bar"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Export Data...", command=self.export_data)
        file_menu.add_command(label="Export Plot...", command=self.export_plot)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # Connection Menu
        conn_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Connection", menu=conn_menu)
        conn_menu.add_command(label="Scan Ports", command=self.scan_serial_ports)
        conn_menu.add_command(label="Connect", command=self.connect_port)
        conn_menu.add_command(label="Disconnect", command=self.disconnect)
        
        # Settings Menu
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="Plot Settings", command=self.show_plot_settings)
        settings_menu.add_command(label="Sampling Rate", command=self.configure_sampling)
        settings_menu.add_separator()
        
        # Use BooleanVar for the checkbutton to properly track its state
        self.auto_scale_var = tk.BooleanVar(value=self.auto_scaling)
        settings_menu.add_checkbutton(label="Auto Scaling", variable=self.auto_scale_var, 
                                     command=self.toggle_auto_scaling)
        
        # Help Menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Documentation", command=self.show_documentation)
        help_menu.add_command(label="About", command=self.show_about)
        
    def scan_serial_ports(self):
        """Scan for available serial ports"""
        try:
            import serial.tools.list_ports
            self.available_ports = [port.device for port in serial.tools.list_ports.comports()]
            if not self.available_ports:
                self.available_ports = ['COM1', 'COM2', 'COM3', 'COM4', 'COM5']  # Fallback
                
            # Update the combobox if it exists and the UI is initialized
            if hasattr(self, 'port_var') and self.port_var is not None:
                try:
                    port_combo = self.root.nametowidget(".!frame.!frame.!labelframe.!frame.!combobox")
                    if port_combo:
                        port_combo['values'] = self.available_ports
                except (KeyError, AttributeError):
                    pass  # Widget might not be ready yet
                    
                if hasattr(self, 'status_var') and self.status_var is not None:
                    self.status_var.set(f"Found {len(self.available_ports)} serial ports")
                
        except Exception as e:
            if hasattr(self, 'status_var') and self.status_var is not None:
                self.status_var.set(f"Error scanning ports: {str(e)}")
            self.available_ports = ['COM1', 'COM2', 'COM3', 'COM4', 'COM5']  # Fallback
    
    def create_communication_manager(self, parent):
        """Create the Communication Manager panel"""
        comm_frame = ttk.LabelFrame(parent, text="Communication Manager", style="Panel.TFrame")
        comm_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Available Ports
        port_frame = ttk.Frame(comm_frame, style="Panel.TFrame")
        port_frame.pack(fill=tk.X, padx=5, pady=5)
        
        port_label = ttk.Label(port_frame, text="Available Ports:", style="Normal.TLabel")
        port_label.pack(side=tk.LEFT, padx=5)
        
        self.port_var = tk.StringVar(value=self.serial_port)
        port_combo = ttk.Combobox(port_frame, textvariable=self.port_var, width=10)
        port_combo['values'] = self.available_ports
        port_combo.pack(side=tk.RIGHT, padx=5)
        
        # Add refresh button for ports
        refresh_btn = ttk.Button(port_frame, text="⟳", width=2, command=self.scan_serial_ports)
        refresh_btn.pack(side=tk.RIGHT, padx=2)
        
        # Baud Rate
        baud_frame = ttk.Frame(comm_frame, style="Panel.TFrame")
        baud_frame.pack(fill=tk.X, padx=5, pady=5)
        
        baud_label = ttk.Label(baud_frame, text="Baud Rate:", style="Normal.TLabel")
        baud_label.pack(side=tk.LEFT, padx=5)
        
        self.baud_var = tk.StringVar(value=str(self.baud_rate))
        baud_combo = ttk.Combobox(baud_frame, textvariable=self.baud_var, width=10)
        baud_combo['values'] = ('4800', '9600', '19200', '38400', '57600', '115200')
        baud_combo.pack(side=tk.RIGHT, padx=5)
        
        # Connect/Disconnect buttons
        btn_frame = ttk.Frame(comm_frame, style="Panel.TFrame")
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        connect_btn = ttk.Button(btn_frame, text="Connect", command=self.connect_port)
        connect_btn.pack(side=tk.LEFT, padx=5)
        
        disconnect_btn = ttk.Button(btn_frame, text="Disconnect", command=self.disconnect)
        disconnect_btn.pack(side=tk.RIGHT, padx=5)
        
    def create_current_details(self, parent):
        """Create the Current Details panel with table"""
        current_frame = ttk.LabelFrame(parent, text="Current Details", style="Panel.TFrame")
        current_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Create table for current values
        columns = ("I_mA1", "I_mA2", "I_mA3", "I_mA4", "I_mA5", "I_mA6")
        self.current_tree = ttk.Treeview(current_frame, columns=columns, show="headings", height=15)
        
        # Configure columns
        for col in columns:
            self.current_tree.heading(col, text=col)
            self.current_tree.column(col, anchor="center", width=60)
            
        self.current_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add some empty rows for display
        for i in range(15):
            self.current_tree.insert("", "end", values=("0.000", "0.000", "0.000", "0.000", "0.000", "0.000"))
    
    def create_total_charge(self, parent):
        """Create the Total Charge Penetrated panel"""
        charge_frame = ttk.LabelFrame(parent, text="Total Charge Penetrated", style="Panel.TFrame")
        charge_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Create table for charge values
        columns = ("Q1", "Q2", "Q3")
        self.charge_tree = ttk.Treeview(charge_frame, columns=columns, show="headings", height=1)
        
        # Configure columns
        for col in columns:
            self.charge_tree.heading(col, text=col)
            self.charge_tree.column(col, anchor="center", width=90)
            
        self.charge_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Add an empty row
        self.charge_tree.insert("", "end", values=("0.0", "0.0", "0.0"))
        
    def create_connection_manager(self, parent):
        """Create the Connection Manager panel"""
        conn_frame = ttk.LabelFrame(parent, text="Connection Manager", style="Panel.TFrame")
        conn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Sync Status
        sync_frame = ttk.Frame(conn_frame, style="Panel.TFrame")
        sync_frame.pack(fill=tk.X, padx=5, pady=5)
        
        sync_label = ttk.Label(sync_frame, text="Sync Status:", style="Normal.TLabel")
        sync_label.pack(side=tk.LEFT, padx=5)
        
        self.sync_var = tk.StringVar(value="--")
        sync_status = ttk.Label(sync_frame, textvariable=self.sync_var, style="Normal.TLabel")
        sync_status.pack(side=tk.LEFT, padx=5)
        
        # Start button
        self.start_btn = ttk.Button(sync_frame, text="Start", command=self.start_recording)
        self.start_btn.pack(side=tk.RIGHT, padx=5)
        
        # Channels
        channel_frame = ttk.Frame(conn_frame, style="Panel.TFrame")
        channel_frame.pack(fill=tk.X, padx=5, pady=5)
        
        channel_label = ttk.Label(channel_frame, text="Channels:", style="Normal.TLabel")
        channel_label.pack(side=tk.LEFT, padx=5)
        
        self.channel_var = tk.StringVar(value="--")
        channel_status = ttk.Label(channel_frame, textvariable=self.channel_var, style="Normal.TLabel")
        channel_status.pack(side=tk.LEFT, padx=5)
        
        # Stop button
        self.stop_btn = ttk.Button(channel_frame, text="Stop", command=self.stop_recording)
        self.stop_btn.pack(side=tk.RIGHT, padx=5)
        self.stop_btn.config(state=tk.DISABLED)
        
    def create_plot_panel(self, parent):
        """Create the Plot panel"""
        plot_frame = ttk.LabelFrame(parent, text="Plot: Current(mA) vs Time(hrs)", style="Panel.TFrame")
        plot_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Set up matplotlib figure
        self.fig = plt.figure(figsize=(8, 6))
        self.ax = self.fig.add_subplot(111)
        
        # Configure axes
        self.ax.set_xlabel('Time(hrs)')
        self.ax.set_ylabel('Current (mA)')
        self.ax.grid(True)
        
        # Create empty lines for initialization
        self.lines = []
        for i in range(6):
            line, = self.ax.plot([], [], lw=2, color=self.line_colors[i], label=f'I{i+1}(mA)')
            self.lines.append(line)
        
        # Add legend
        self.ax.legend(loc='upper right')
        
        # Display the plot in Tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
    def create_status_bar(self, parent):
        """Create status bar at the bottom"""
        status_frame = ttk.Frame(parent, style="Panel.TFrame")
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=5)
        
        self.status_var = tk.StringVar(value="Ready. Connect to serial port and press Start to begin recording.")
        status_label = ttk.Label(status_frame, textvariable=self.status_var, style="Normal.TLabel")
        status_label.pack(side=tk.LEFT, padx=5)
        
        # NPAV Protection indication
        npav_label = ttk.Label(status_frame, text="NPAV Protected", style="Normal.TLabel")
        npav_label.pack(side=tk.RIGHT, padx=5)
        
    def create_plot_settings_dialog(self):
        """Create a popup dialog for plot settings"""
        self.plot_settings_window = None
    
    def connect_port(self):
        """Connect to the selected serial port"""
        try:
            # Get COM port and baud rate from UI
            self.serial_port = self.port_var.get()
            self.baud_rate = int(self.baud_var.get())
            
            # Close existing connection if any
            if self.ser and self.ser.is_open:
                self.ser.close()
                
            # Attempt to open serial connection
            self.ser = serial.Serial(self.serial_port, self.baud_rate, timeout=1)
            self.status_var.set(f"Connected to {self.serial_port} at {self.baud_rate} baud")
            
        except Exception as e:
            messagebox.showerror("Connection Error", f"Could not open port {self.serial_port}:\n{str(e)}")
            self.status_var.set(f"Connection error: {str(e)}")
    
    def start_recording(self):
        """Start recording data from serial port"""
        try:
            # Check if we're already connected, connect if not
            if not (self.ser and self.ser.is_open):
                self.connect_port()
            
            if not (self.ser and self.ser.is_open):
                # If still not connected, abort
                return
            
            # Reset data
            self.current_data = [[] for _ in range(6)]
            self.time_stamps = []
            self.datetime_stamps = []
            self.time_counter = 0
            self.total_charge = [0.0, 0.0, 0.0]
                
            # Update state
            self.is_recording = True
            self.start_time = datetime.now()
            
            # Update UI
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.sync_var.set("OK")
            self.channel_var.set("6")
            self.status_var.set(f"Recording started on port {self.serial_port}...")
            
            # Start data collection in a separate thread
            self.collection_thread = threading.Thread(target=self.collect_data, daemon=True)
            self.collection_thread.start()
            
        except Exception as e:
            messagebox.showerror("Recording Error", f"Could not start recording:\n{str(e)}")
            self.status_var.set(f"Recording error: {str(e)}")
    
    def stop_recording(self):
        """Stop recording data"""
        if self.is_recording:
            self.is_recording = False
            
            # Update UI
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.sync_var.set("--")
            self.status_var.set(f"Recording stopped. Collected {len(self.time_stamps)} data points.")
    
    def disconnect(self):
        """Disconnect from serial port"""
        self.stop_recording()
        
        # Close serial connection if open
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
                self.status_var.set("Disconnected from serial port.")
            except Exception as e:
                self.status_var.set(f"Error disconnecting: {str(e)}")
        else:
            self.status_var.set("Not connected to any port.")
    
    def export_data(self):  # Fixed: Fixed indentation
        """Export collected data to Excel file"""
        if not self.time_stamps:
            messagebox.showinfo("Export Info", "No data available to export.")
            return
            
        try:
            # Format timestamps
            formatted_times = [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in self.datetime_stamps]
            
            # Create DataFrame
            data_dict = {
                'Timestamp': formatted_times,
                'Time(hrs)': self.time_stamps
            }
            
            # Add current data
            for i in range(6):
                data_dict[f'I{i+1}(mA)'] = self.current_data[i]
            
            df = pd.DataFrame(data_dict)
            
            # Let user choose save location
            current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"current_data_{current_time}.xlsx"
            file_path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                filetypes=[("Excel Files", ".xlsx"), ("CSV Files", ".csv"), ("All Files", ".")],
                initialfile=default_filename
            )
            
            if not file_path:
                return  # User canceled
                
            # Export based on file extension
            if file_path.endswith('.xlsx'):
                df.to_excel(file_path, index=False)
                
                try:
                    # Create a second sheet with statistics
                    with pd.ExcelWriter(file_path, engine='openpyxl', mode='a') as writer:
                        # Create stats dataframe
                        stats_data = {
                            'Metric': ['Minimum', 'Maximum', 'Average', 'Standard Deviation']
                        }
                        
                        # Add stats for each channel
                        for i in range(6):
                            if self.current_data[i]:
                                stats_data[f'I{i+1}(mA)'] = [
                                    min(self.current_data[i]),
                                    max(self.current_data[i]),
                                    sum(self.current_data[i]) / len(self.current_data[i]),
                                    np.std(self.current_data[i])
                                ]
                        
                        stats_df = pd.DataFrame(stats_data)
                        stats_df.to_excel(writer, sheet_name='Statistics', index=False)
                        
                        # Add charge data
                        charge_data = {
                            'Channel': ['Q1', 'Q2', 'Q3'],
                            'Total Charge': self.total_charge
                        }
                        charge_df = pd.DataFrame(charge_data)
                        charge_df.to_excel(writer, sheet_name='Charge Data', index=False)
                except Exception as e:
                    messagebox.showwarning("Statistics Warning", 
                                          f"Data exported but statistics could not be added:\n{str(e)}")
                    
            elif file_path.endswith('.csv'):
                df.to_csv(file_path, index=False)
                
            self.status_var.set(f"Data exported successfully to {os.path.basename(file_path)}")
            messagebox.showinfo("Export Successful", f"Data has been exported to {file_path}")
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export data:\n{str(e)}")
            self.status_var.set(f"Export error: {str(e)}")

    def show_plot_settings(self):
        """Show the plot settings dialog"""
        if self.plot_settings_window is not None:
            self.plot_settings_window.destroy()
            
        self.plot_settings_window = tk.Toplevel(self.root)
        self.plot_settings_window.title("Plot Settings")
        self.plot_settings_window.geometry("400x300")
        self.plot_settings_window.transient(self.root)
        self.plot_settings_window.grab_set()
        
        # Settings frame
        settings_frame = ttk.Frame(self.plot_settings_window, padding=10)
        settings_frame.pack(fill=tk.BOTH, expand=True)
        
        # Auto scaling
        auto_scale_var = tk.BooleanVar(value=self.auto_scaling)
        auto_scale_chk = ttk.Checkbutton(settings_frame, text="Auto Scale Y-Axis", 
                                         variable=auto_scale_var)
        auto_scale_chk.pack(anchor=tk.W, pady=5)
        
        # Channel visibility
        ttk.Label(settings_frame, text="Channel Visibility:").pack(anchor=tk.W, pady=5)
        
        channel_vars = []
        for i in range(6):
            var = tk.BooleanVar(value=True)
            channel_vars.append(var)
            ttk.Checkbutton(settings_frame, text=f"Channel {i+1}", variable=var).pack(anchor=tk.W, padx=20)
        
        # Display time range
        ttk.Label(settings_frame, text="Display Time Range (hours):").pack(anchor=tk.W, pady=5)
        time_range_var = tk.DoubleVar(value=2.0)
        time_range_scale = ttk.Scale(settings_frame, from_=0.5, to=24.0, variable=time_range_var,
                                     orient=tk.HORIZONTAL, length=200)
        time_range_scale.pack(anchor=tk.W, padx=20)
        
        time_label = ttk.Label(settings_frame, text="2.0 hours")
        time_label.pack(anchor=tk.W, padx=20)
        
        # Update label when scale is moved
        def update_time_label(event):
            time_label.config(text=f"{time_range_var.get():.1f} hours")
        
        time_range_scale.bind("<Motion>", update_time_label)
        
        # Buttons
        btn_frame = ttk.Frame(settings_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        def apply_settings():
            self.auto_scaling = auto_scale_var.get()
            # Apply other settings here
            self.update_plot()
            self.plot_settings_window.destroy()
            self.plot_settings_window = None
            
        ttk.Button(btn_frame, text="Apply", command=apply_settings).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=lambda: self.plot_settings_window.destroy()).pack(side=tk.RIGHT, padx=5)
    
    def configure_sampling(self):
        """Configure the data sampling rate"""
        sampling_window = tk.Toplevel(self.root)
        sampling_window.title("Sampling Rate")
        sampling_window.geometry("300x150")
        sampling_window.transient(self.root)
        sampling_window.grab_set()
        
        frame = ttk.Frame(sampling_window, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="Sampling interval (seconds):").pack(anchor=tk.W, pady=5)
        
        interval_var = tk.DoubleVar(value=self.data_interval)
        interval_entry = ttk.Entry(frame, textvariable=interval_var, width=10)
        interval_entry.pack(anchor=tk.W, pady=5)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=10)
        
        def apply_sampling():
            try:
                new_interval = float(interval_var.get())
                if new_interval > 0:
                    self.data_interval = new_interval
                    self.status_var.set(f"Sampling interval set to {self.data_interval} seconds")
                    sampling_window.destroy()
                else:
                    messagebox.showerror("Invalid Value", "Sampling interval must be greater than 0")
            except ValueError:
                messagebox.showerror("Invalid Value", "Please enter a valid number")
                
        ttk.Button(btn_frame, text="Apply", command=apply_sampling).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=sampling_window.destroy).pack(side=tk.RIGHT, padx=5)
    
    def toggle_auto_scaling(self):
        """Toggle auto-scaling of the Y-axis"""
        self.auto_scaling = not self.auto_scaling
        self.update_plot()
        self.status_var.set(f"Auto scaling {'enabled' if self.auto_scaling else 'disabled'}")
    
    def show_documentation(self):
        """Show the application documentation"""
        doc_window = tk.Toplevel(self.root)
        doc_window.title("Documentation")
        doc_window.geometry("600x400")
        
        text_widget = tk.Text(doc_window, wrap=tk.WORD, padx=10, pady=10)
        text_widget.pack(fill=tk.BOTH, expand=True)
        
        # Add a scrollbar
        scrollbar = ttk.Scrollbar(text_widget, command=text_widget.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        # Documentation content
        documentation = """
# Current Monitoring System Documentation

## Overview
This application allows you to monitor and record current measurements from multiple channels through a serial connection.

## Getting Started
1. Select the appropriate COM port from the Communication Manager
2. Set the correct baud rate
3. Click 'Connect' to establish a connection
4. Click 'Start' in the Connection Manager to begin recording

## Features
- Real-time monitoring of up to 6 current channels
- Automatic calculation of total charge
- Data export to Excel or CSV
- Customizable plot settings

## Keyboard Shortcuts
- Ctrl+S: Start recording
- Ctrl+P: Stop recording
- Ctrl+E: Export data
- Ctrl+Q: Quit application

## Troubleshooting
If you encounter connection issues:
- Verify the device is properly connected
- Check that you've selected the correct COM port
- Ensure you're using the correct baud rate
- Try disconnecting and reconnecting

For additional help, contact support at support@vedantrik.com
        """
        
        text_widget.insert(tk.END, documentation)
        text_widget.config(state=tk.DISABLED)  # Make read-only
    
    def show_about(self):
        """Show information about the application"""
        messagebox.showinfo("About", 
                           "Current Monitoring System\n"
                           "Version 1.0.0\n\n"
                           "© 2025 Vedantrik Technologies\n"
                           "All rights reserved.")
    
    def export_plot(self):
        """Export the current plot as an image"""
        if not self.time_stamps:
            messagebox.showinfo("Export Info", "No data available to export plot.")
            return
            
        try:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG Files", ".png"), ("JPEG Files", ".jpg"), ("PDF Files", ".pdf"), ("SVG Files", ".svg")]
            )
            
            if not file_path:
                return  # User canceled
                
            # Export the figure
            self.fig.savefig(file_path, dpi=300, bbox_inches='tight')
            self.status_var.set(f"Plot exported to {os.path.basename(file_path)}")
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export plot:\n{str(e)}")
            self.status_var.set(f"Plot export error: {str(e)}")
            
    def collect_data(self):
        """Collect and process data from the serial port"""
        try:
            while self.is_recording:
                if self.ser and self.ser.is_open:
                    # Read data from serial port
                    try:
                        line = self.ser.readline().decode('utf-8').strip()
                        if line:
                            # Process the received data
                            # Assuming format: "I1,I2,I3,I4,I5,I6"
                            values = line.split(',')
                            if len(values) >= 6:
                                # Convert and store the values
                                for i in range(6):
                                    try:
                                        current_value = float(values[i])
                                        self.current_data[i].append(current_value)
                                        
                                        # Limit the data points to avoid memory issues
                                        if len(self.current_data[i]) > self.max_data_points:
                                            self.current_data[i].pop(0)
                                    except (ValueError, IndexError):
                                        self.current_data[i].append(0.0)  # Default on error
                                
                                # Calculate time in hours
                                current_time = datetime.now()
                                time_diff = (current_time - self.start_time).total_seconds() / 3600.0  # hours
                                
                                self.time_stamps.append(time_diff)
                                self.datetime_stamps.append(current_time)
                                
                                # Limit time stamps data
                                if len(self.time_stamps) > self.max_data_points:
                                    self.time_stamps.pop(0)
                                    self.datetime_stamps.pop(0)
                                
                                # Update total charge (in coulombs) for first 3 channels
                                # Q = I * t where t is in seconds
                                interval_sec = self.data_interval  # time between samples in seconds
                                for i in range(min(3, len(values))):
                                    try:
                                        # I in mA, convert to A by dividing by 1000
                                        current_in_amps = float(values[i]) / 1000.0
                                        self.total_charge[i] += current_in_amps * interval_sec
                                    except (ValueError, IndexError):
                                        pass
                                
                                # Update the UI
                                self.update_ui()
                    except Exception as e:
                        self.status_var.set(f"Data reading error: {str(e)}")
                
                # Wait for the next interval
                time.sleep(self.data_interval)
        except Exception as e:
            self.status_var.set(f"Data collection error: {str(e)}")
            self.is_recording = False
            if self.start_btn:
                self.start_btn.config(state=tk.NORMAL)
            if self.stop_btn:
                self.stop_btn.config(state=tk.DISABLED)
    
    def update_ui(self):
        """Update the UI with new data"""
        try:
            # Update current table
            if self.current_data[0] and self.current_tree:
                # Get the last values for all channels
                last_values = [
                    f"{self.current_data[i][-1]:.3f}" if self.current_data[i] else "0.000" 
                    for i in range(6)
                ]
                
                # Update first row with latest values
                items = self.current_tree.get_children()
                if items:
                    self.current_tree.item(items[0], values=last_values)
                    
                    # Shift other rows down
                    for i in range(1, len(items)):
                        previous_values = self.current_tree.item(items[i-1], 'values')
                        self.current_tree.item(items[i], values=previous_values)
            
            # Update charge table
            if self.charge_tree:
                charge_values = [f"{charge:.3f}" for charge in self.total_charge]
                items = self.charge_tree.get_children()
                if items:
                    self.charge_tree.item(items[0], values=charge_values)
            
            # Update plot
            self.update_plot()
            
        except Exception as e:
            self.status_var.set(f"UI update error: {str(e)}")
    
    def update_plot(self):
        """Update the plot with new data"""
        try:
            if not self.time_stamps:
                return  # No data to plot
                
            # Update each line with the available data
            for i in range(6):
                if self.current_data[i]:
                    # Ensure data lengths match
                    data_length = min(len(self.time_stamps), len(self.current_data[i]))
                    time_data = self.time_stamps[-data_length:]
                    current_data = self.current_data[i][-data_length:]
                    
                    self.lines[i].set_data(time_data, current_data)
            
            # Adjust axes limits
            if self.time_stamps:
                self.ax.set_xlim(max(0, self.time_stamps[-1] - 2.0), max(2.0, self.time_stamps[-1]))
                
                if self.auto_scaling:
                    # Find min and max across all channels
                    all_data = []
                    for i in range(6):
                        if self.current_data[i]:
                            all_data.extend(self.current_data[i][-50:])  # Consider last 50 points for scaling
                    
                    if all_data:
                        data_min = min(all_data)
                        data_max = max(all_data)
                        margin = max(0.1, (data_max - data_min) * 0.1)  # 10% margin
                        self.ax.set_ylim(max(0, data_min - margin), data_max + margin)
            
            # Refresh the plot
            self.canvas.draw_idle()
            
        except Exception as e:
            self.status_var.set(f"Plot update error: {str(e)}")


# Add any missing methods here as needed

# Main execution
if __name__ == "__main__":  # Fixed: Changed _main_ to __main__
    try:
        # Set up error logging
        import logging
        logging.basicConfig(filename='current_monitor.log', level=logging.ERROR,
                           format='%(asctime)s - %(levelname)s - %(message)s')
        
        # Configure ttk styles
        root = tk.Tk()
        app = CurrentMonitoringSystem(root)
        
        # Set window icon if available
        try:
            root.iconbitmap('vedantrik_icon.ico')
        except:
            pass  # If icon file is not available
        
        # Create a splash screen
        splash = tk.Toplevel(root)
        splash.title("Loading...")
        splash.geometry("400x200")
        splash.overrideredirect(True)  # Remove window decorations
        
        # Center the splash screen
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = (screen_width - 400) // 2
        y = (screen_height - 200) // 2
        splash.geometry(f"400x200+{x}+{y}")
        
        # Add splash content
        splash_frame = ttk.Frame(splash)
        splash_frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(splash_frame, text="VEDANTRIK TECHNOLOGIES", font=("Arial", 16, "bold")).pack(pady=20)
        ttk.Label(splash_frame, text="Current Monitoring System", font=("Arial", 12)).pack(pady=10)
        ttk.Label(splash_frame, text="Loading...").pack(pady=20)
        
        # Progress bar
        progress = ttk.Progressbar(splash_frame, mode='indeterminate')
        progress.pack(fill=tk.X, padx=20, pady=10)
        progress.start(10)
        
        # Function to close splash and show main window
        def close_splash():
            splash.destroy()
            root.deiconify()  # Show the main window
            
            # Center the main window too
            window_width = root.winfo_width()
            window_height = root.winfo_height()
            main_x = (screen_width - window_width) // 2
            main_y = (screen_height - window_height) // 2
            root.geometry(f"+{main_x}+{main_y}")
        
        # Hide main window during splash
        root.withdraw()
        
        # Schedule splash closure
        root.after(2000, close_splash)
        
        # Add keyboard shortcuts
        root.bind("<Control-s>", lambda e: app.start_recording())
        root.bind("<Control-p>", lambda e: app.stop_recording())
        root.bind("<Control-e>", lambda e: app.export_data())
        root.bind("<Control-q>", lambda e: root.quit())
        
        # Set up auto-save functionality
        def schedule_autosave():
            if app.is_recording and len(app.time_stamps) > 0:
                try:
                    # Create backup directory if it doesn't exist
                    os.makedirs("autosave", exist_ok=True)
                    
                    # Auto-save with timestamp
                    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"autosave/current_data_autosave_{current_time}.xlsx"
                    
                    # Format timestamps
                    formatted_times = [dt.strftime("%Y-%m-%d %H:%M:%S") for dt in app.datetime_stamps]
                    
                    # Create DataFrame
                    data_dict = {
                        'Timestamp': formatted_times,
                        'Time(hrs)': app.time_stamps
                    }
                    
                    # Add current data
                    for i in range(6):
                        data_dict[f'I{i+1}(mA)'] = app.current_data[i]
                    
                    df = pd.DataFrame(data_dict)
                    df.to_excel(filename, index=False)
                    
                    app.status_var.set(f"Auto-saved data to {os.path.basename(filename)}")
                except Exception as e:
                    logging.error(f"Auto-save error: {str(e)}")
                
            # Schedule next auto-save after 5 minutes
            root.after(300000, schedule_autosave)
            
        # Start auto-save scheduling
        root.after(300000, schedule_autosave)
        
        # Run the application
        root.mainloop()
        
    except Exception as e:
        # Handle any uncaught exceptions
        print(f"Application error: {str(e)}")
        logging.error(f"Critical application error: {str(e)}")
        
        # If GUI is available, show error dialog
        try:
            messagebox.showerror("Critical Error", f"Application encountered an error:\n{str(e)}")
        except:
            pass