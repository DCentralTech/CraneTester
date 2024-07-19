import sys
import time
import binascii
from PyQt5.QtWidgets import (QApplication, QMainWindow, QGridLayout, QWidget, QPushButton, 
                             QLabel, QComboBox, QVBoxLayout, QHBoxLayout, QMessageBox, 
                             QTextEdit, QScrollArea, QSlider)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
import serial
import serial.tools.list_ports

MINER_CONFIGS = {
    'Antminer S17': {'chips': 45, 'has_pic': True},
    'Antminer S19k Pro': {'chips': 126, 'has_pic': False},
    # Add other models as needed
}

class BitcraneThread(QThread):
    update_signal = pyqtSignal(int, bool)
    log_signal = pyqtSignal(str)

    def __init__(self, parent, port, model):
        super().__init__(parent)
        self.port = port
        self.model = model
        self.is_running = True
        self.serial_port = None

    def run(self):
        try:
            self.initialize_bitcrane()
            self.log_signal.emit(f"Connected to Bitcrane on {self.port}")
            
            if not self.ping_bitcrane():
                self.log_signal.emit("Failed to ping Bitcrane. Check connections.")
                return

            self.power_on_hashboard()
            
            config = MINER_CONFIGS[self.model]
            for chip in range(config['chips']):
                if not self.is_running:
                    break
                if self.detect_chip(chip):
                    temp = self.read_temperature(chip)
                    self.log_signal.emit(f"Chip {chip} detected, temp: {temp}")
                    self.update_signal.emit(chip, True)
                else:
                    self.log_signal.emit(f"Chip {chip} not detected")
                    self.update_signal.emit(chip, False)
                time.sleep(0.1)
        except Exception as e:
            self.log_signal.emit(f"Error: {str(e)}")
        finally:
            self.cleanup()

    def initialize_bitcrane(self):
        try:
            self.serial_port = serial.Serial(self.port, baudrate=115200, timeout=1)
            self.log_signal.emit(f"Connected to {self.port}")
        except Exception as e:
            self.log_signal.emit(f"Initialization error: {str(e)}")
            raise

    def cleanup(self):
        if self.serial_port:
            self.serial_port.close()

    def stop(self):
        self.is_running = False

    def ping_bitcrane(self):
        command = bytes([0x55, 0xAA, 0x51, 0x09, 0x00, 0xA4, 0x90, 0x00, 0xFF, 0xFF, 0x1C])
        self.log_signal.emit(f"Sending ping: {binascii.hexlify(command)}")
        self.serial_port.write(command)
        response = self.serial_port.read(11)
        self.log_signal.emit(f"Ping response: {binascii.hexlify(response)}")
        return len(response) > 0

    def power_on_hashboard(self):
        command = bytes([0x55, 0xAA, 0x52, 0x05, 0x00, 0x00, 0x0A])
        self.log_signal.emit(f"Sending power-on command: {binascii.hexlify(command)}")
        self.serial_port.write(command)
        response = self.serial_port.read(7)
        self.log_signal.emit(f"Power-on response: {binascii.hexlify(response)}")

    def detect_chip(self, chip_index):
        command = self.create_read_command(chip_index)
        self.log_signal.emit(f"Sending chip detect command: {binascii.hexlify(command)}")
        self.serial_port.write(command)
        response = self.serial_port.read(9)  # Assuming 9-byte response
        self.log_signal.emit(f"Chip detect response: {binascii.hexlify(response)}")
        return self.parse_response(response)

    def read_temperature(self, chip_index):
        command = self.create_temp_command(chip_index)
        self.log_signal.emit(f"Sending temp read command: {binascii.hexlify(command)}")
        self.serial_port.write(command)
        response = self.serial_port.read(9)  # Assuming 9-byte response
        self.log_signal.emit(f"Temp read response: {binascii.hexlify(response)}")
        return self.parse_temp_response(response)

    def create_read_command(self, chip_index):
        return bytes([0x55, 0xAA, 0x01, 0x00, chip_index, 0x00, 0x00, 0x00])

    def create_temp_command(self, chip_index):
        return bytes([0x55, 0xAA, 0x02, 0x00, chip_index, 0x00, 0x00, 0x00])

    def parse_response(self, response):
        return len(response) == 9 and response[0] == 0xAA and response[1] == 0x55

    def parse_temp_response(self, response):
        if len(response) == 9 and response[0] == 0xAA and response[1] == 0x55:
            return response[2]  # Assuming temperature is in the 3rd byte
        return None

    def set_fan_speed(self, speed):
        command = bytes([0x55, 0xAA, 0x03, 0x00, speed, 0x00, 0x00, 0x00])
        self.log_signal.emit(f"Sending fan speed command: {binascii.hexlify(command)}")
        self.serial_port.write(command)
        response = self.serial_port.read(8)
        self.log_signal.emit(f"Fan speed response: {binascii.hexlify(response)}")

class BitcraneTester(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.test_thread = None

    def initUI(self):
        self.setWindowTitle('Bitcrane Hashboard Tester')
        self.setGeometry(100, 100, 1000, 800)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        # Miner model and device selection
        selection_layout = QHBoxLayout()
        selection_layout.addWidget(QLabel("Miner Model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(MINER_CONFIGS.keys())
        self.model_combo.currentTextChanged.connect(self.update_layout)
        selection_layout.addWidget(self.model_combo)

        selection_layout.addWidget(QLabel("Bitcrane Port:"))
        self.port_combo = QComboBox()
        self.update_port_list()
        selection_layout.addWidget(self.port_combo)

        main_layout.addLayout(selection_layout)

        # Fan speed control
        fan_layout = QHBoxLayout()
        fan_layout.addWidget(QLabel("Fan Speed:"))
        self.fan_slider = QSlider(Qt.Horizontal)
        self.fan_slider.setRange(0, 100)
        self.fan_slider.setValue(50)
        self.fan_slider.valueChanged.connect(self.set_fan_speed)
        fan_layout.addWidget(self.fan_slider)
        main_layout.addLayout(fan_layout)

        # Chip grid
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        grid_widget = QWidget()
        self.grid_layout = QGridLayout(grid_widget)
        scroll_area.setWidget(grid_widget)
        main_layout.addWidget(scroll_area)

        # Buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton('Start Test')
        self.start_button.clicked.connect(self.start_test)
        button_layout.addWidget(self.start_button)

        self.stop_button = QPushButton('Stop Test')
        self.stop_button.clicked.connect(self.stop_test)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.stop_button)

        main_layout.addLayout(button_layout)

        # Log area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        main_layout.addWidget(self.log_text)

        self.update_layout(self.model_combo.currentText())

    def update_port_list(self):
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(port.device)
        if self.port_combo.count() == 0:
            self.port_combo.addItem("No COM ports found")

    def update_layout(self, model):
        # Clear existing layout
        for i in reversed(range(self.grid_layout.count())): 
            self.grid_layout.itemAt(i).widget().setParent(None)

        self.chip_buttons = []
        chips = MINER_CONFIGS[model]['chips']
        for i in range(chips):
            button = QPushButton(f'Chip {i+1}')
            button.setFixedSize(60, 60)
            self.grid_layout.addWidget(button, i // 10, i % 10)
            self.chip_buttons.append(button)

    def start_test(self):
        if self.test_thread and self.test_thread.isRunning():
            return

        model = self.model_combo.currentText()
        port = self.port_combo.currentText()

        if port == "No COM ports found":
            QMessageBox.warning(self, "Error", "No valid COM port selected.")
            return

        # Reset all buttons to default state
        for button in self.chip_buttons:
            button.setStyleSheet("background-color: grey")

        self.log_text.clear()
        self.log_text.append(f"Starting test for {model} on port {port}")

        self.test_thread = BitcraneThread(self, port, model)
        self.test_thread.update_signal.connect(self.update_chip_status)
        self.test_thread.log_signal.connect(self.log_message)
        self.test_thread.finished.connect(self.test_finished)
        self.test_thread.start()

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    def stop_test(self):
        if self.test_thread and self.test_thread.isRunning():
            self.test_thread.stop()
            self.log_text.append("Stopping test...")

    def update_chip_status(self, chip_index, status):
        self.chip_buttons[chip_index].setStyleSheet(
            "background-color: green" if status else "background-color: red")

    def log_message(self, message):
        self.log_text.append(message)

    def test_finished(self):
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.log_text.append("Test finished")

    def set_fan_speed(self, speed):
        if self.test_thread and self.test_thread.is_running:
            self.test_thread.set_fan_speed(speed)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    tester = BitcraneTester()
    tester.show()
    sys.exit(app.exec_())