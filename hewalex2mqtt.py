import appdaemon.plugins.hass.hassapi as hass
import os
import threading
import configparser
import serial
from hewalex_geco.devices import PCWU
import paho.mqtt.client as mqtt
import logging
import sys

# The class definition for the AppDaemon app
class Hewalex2MQTT(hass.Hass):
    # Declare dev as a class attribute
    dev = None

    # Your app initialization logic here
    def initialize(self):
        # polling interval
        self.get_status_interval = 30.0
        
        # Controller (Master)
        self.conHardId = 1
        self.conSoftId = 1
        
        # PCWU (Slave)
        self.devHardId = 2
        self.devSoftId = 2

        #mqtt
        self.flag_connected_mqtt = 0
        self.MessageCache = {}

        # Initialize the logger
        self.initLogger()

        # Initialize the configuration first
        self.initConfiguration()

        # Start MQTT connection
        self.start_mqtt()

        # Declare dev as a class attribute
        self.dev = PCWU(self.conHardId, self.conSoftId, self.devHardId, self.devSoftId, self.on_message_serial)

        # Call device_readregisters_enqueue to start the periodic task
        self.device_readregisters_enqueue()

    def initLogger(self):
        # Set up the logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        # Controleer of de logger al handlers heeft om dubbele logging te voorkomen
        if not self.logger.hasHandlers():
            formatter = logging.Formatter('%(asctime)s :: %(name)s :: %(levelname)s :: %(message)s')
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setFormatter(formatter)
            stream_handler.setLevel(logging.INFO)
            
            # Voeg alleen de handler toe als er nog geen handler is
            self.logger.addHandler(stream_handler)
        
        self.logger.info("Initializing Hewalex 2 Mqtt")

    # Read Configs
    def initConfiguration(self):
        self.logger.info("reading config")
        config_file = os.path.join(os.path.dirname(__file__), 'hewalex2mqttconfig.ini')
        config = configparser.ConfigParser()
        config.read(config_file)
    
        # Mqtt
        self._MQTT_ip = config.get('MQTT', 'MQTT_ip')
        self._MQTT_port = config.getint('MQTT', 'MQTT_port')
        self._MQTT_authentication = config.getboolean('MQTT', 'MQTT_authentication')
        self._MQTT_user = config.get('MQTT', 'MQTT_user')
        self._MQTT_pass = config.get('MQTT', 'MQTT_pass')
        self.logger.info(f'MQTT ip: {self._MQTT_ip}')
        self.logger.info(f'MQTT port: {self._MQTT_port}')
        self.logger.info(f'MQTT authentication: {self._MQTT_authentication}')
        self.logger.info(f'MQTT user: {self._MQTT_user}')
        self.logger.info(f'MQTT pass: {self._MQTT_pass}')

        # PCWU Device
        self._Device_Pcwu_Enabled = config.getboolean('Pcwu', 'Device_Pcwu_Enabled')
        if self._Device_Pcwu_Enabled:
            self._Device_Pcwu_Address = config.get('Pcwu', 'Device_Pcwu_Address')
            self._Device_Pcwu_Port = config.getint('Pcwu', 'Device_Pcwu_Port')
            self._Device_Pcwu_MqttTopic = config.get('Pcwu', 'Device_Pcwu_MqttTopic')
            self.logger.info(f'Device_Pcwu_MqttTopic: {self._Device_Pcwu_MqttTopic}')
    
        # Use the values as needed in your app
        if self._Device_Pcwu_Enabled:
            # Create the serial connection with the correct baudrate
            # Do something with self._Device_Pcwu_Address, self._Device_Pcwu_Port, and self._Device_Pcwu_MqttTopic
            # For example, assign them to class attributes
            pass
        else:
            # Handle the case when Pcwu is not enabled
            pass

    def on_message_mqtt(self, client, userdata, message):
        self.logger.info("Received message with topic: {}".format(message.topic))
        self.logger.info("Received command: {}".format(message.payload.decode('utf-8')))

        # Verwerkt commando's bedoeld voor PCWU-apparaat
        if message.topic.startswith(f"{self._Device_Pcwu_MqttTopic}/Command/"):
            register_name = message.topic.split('/')[-1]  # Extract the register name from the topic
            command_value = message.payload.decode('utf-8')
            self.logger.info(f"Received command to set {register_name} to {command_value}")
            self.writePcwuConfig(register_name, command_value)
        else:
            # Handle other MQTT messages if needed
            self.logger.info("Received unrelated MQTT message, no action taken.")
        
    def writePcwuConfig(self, registerName, payload):
        # Log the attempt to write to the PCWU device
        self.logger.info(f"Attempting to write to register: {registerName} with value: {payload}")
        try:
        # Open the serial connection
            with serial.serial_for_url(f"socket://{self._Device_Pcwu_Address}:{self._Device_Pcwu_Port}", baudrate=38400, timeout=2, write_timeout=2) as ser:
                # Call the write function on the PCWU device
                result = self.dev.write(ser, registerName, payload)
                # Check if the write was successful
                if result:
                    self.logger.info(f"Successfully wrote {payload} to {registerName}")
                else:
                    self.logger.error(f"Failed to write {payload} to {registerName}")
        except Exception as e:
            self.logger.error(f"Error writing to PCWU: {e}")



    # Define flag_connected_mqtt as a global variable at the beginning of the script
    #flag_connected_mqtt = 0
    def log_mqtt_status(self, kwargs):
        if self.flag_connected_mqtt == 1:
            self.logger.info("MQTT Broker is connected.")
        else:
            self.logger.info("MQTT Broker is disconnected.")

    def start_mqtt(self):
        self.mqtt_client = mqtt.Client()
        if self._MQTT_authentication:
            self.mqtt_client.username_pw_set(username=self._MQTT_user, password=self._MQTT_pass)
            
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
        self.mqtt_client.on_message = self.on_message_mqtt
        # self.mqtt_client.enable_logger(self.logger)
        self.mqtt_client.connect(self._MQTT_ip, self._MQTT_port)
        if self._Device_Pcwu_Enabled:
            self.logger.info('Subscribed to: ' + self._Device_Pcwu_MqttTopic + '/Command/#')
            self.mqtt_client.subscribe(self._Device_Pcwu_MqttTopic + '/Command/#', qos=1)

        self.mqtt_client.loop_start()
    
    def on_mqtt_connect(self, client, userdata, flags, rc):
        self.logger.info("Verbonden to MQTT Broker with result code: {}".format(rc))
        # Update dit om te abonneren op het correcte topic dat overeenkomt met je MQTT configuratie voor PCWU
        base_topic = f"{self._Device_Pcwu_MqttTopic}/#"  # Abonneer op alle subtopics onder je basis PCWU topic
        self.mqtt_client.subscribe(base_topic)
        self.logger.info(f"ABBOSubscribed to MQTT topic: {base_topic}")
        self.flag_connected_mqtt = 1
    
    def on_mqtt_disconnect(self, client, userdata, rc):
        self.logger.info("Disconnected from MQTT Broker with result code: {}".format(rc))
        self.flag_connected_mqtt = 0
    
    def on_message_serial(self, obj, h, sh, m):
        #self.logger.info(f'on_message_serial flag_connected_mqtt: {self.flag_connected_mqtt}')
        #self.logger.info('on_message_serial')
        #self.logger.info(f'MessageCache obj: {obj}')
        #self.logger.info(f'MessageCache h: {h}')
        #self.logger.info(f'MessageCache sh: {sh}')
        #self.logger.info(f'MessageCache m: {m}')
        try:    
            if self.flag_connected_mqtt != 1:
                self.logger.info('on_message_serial not connected to mqtt')
                return False
            
            global MessageCache
            topic = self._Device_Pcwu_MqttTopic
            if sh["FNC"] == 0x50:
                mp = obj.parseRegisters(sh["RestMessage"], sh["RegStart"], sh["RegLen"])        
                for item in mp.items():
                    if isinstance(item[1], dict): # skipping dictionaries (time program) 
                        continue
                    key = topic + '/' + str(item[0])
                    val = str(item[1])
                    if key not in self.MessageCache or self.MessageCache[key] != val:
                        self.MessageCache[key] = val
                        self.logger.info(key + " " + val)
                        self.mqtt_client.publish(key, val)
    
        except Exception as e:
            self.logger.info('Exception in on_message_serial: '+ str(e))
    
    def device_readregisters_enqueue(self):
        """Get device status every x seconds"""
        #self.logger.info('Get device status')
        #self.logger.info(f'device_readregisters_enqueue flag_connected_mqtt: {self.flag_connected_mqtt}')
        threading.Timer(self.get_status_interval, self.device_readregisters_enqueue).start()
        if self._Device_Pcwu_Enabled:        
            self.readPCWU()
            self.readPcwuConfig()

    def readPCWU(self):    
        # Controleer en log de waarden van de attributen
        self.logger.info(f"Connecting to PCWU at {self._Device_Pcwu_Address}:{self._Device_Pcwu_Port}")
        try:
            with serial.serial_for_url(f"socket://{self._Device_Pcwu_Address}:{self._Device_Pcwu_Port}") as ser:
                self.logger.info("Serial connection established.")
                self.dev = PCWU(self.conHardId, self.conSoftId, self.devHardId, self.devSoftId, self.on_message_serial)
                read_data = self.dev.readStatusRegisters(ser)
                # Log alleen of er data ontvangen is of niet, zonder de data zelf te tonen
                if read_data:
                    self.logger.info("Data successfully received from PCWU.")
                else:
                    self.logger.info("No data received from PCWU.")
        except Exception as e:
            self.logger.error(f"Error in readPCWU: {e}")

    
    def readPcwuConfig(self):    
        #self.logger.info(f'readPcwuConfig flag_connected_mqtt: {self.flag_connected_mqtt}')
        ser = serial.serial_for_url("socket://%s:%s" % (self._Device_Pcwu_Address, self._Device_Pcwu_Port), baudrate=38400, timeout=2)
        #self.logger.info(f'readPCWUConfig: {ser}')
        self.dev.readConfigRegisters(ser)
        ser.close()
  
   
    def printPcwuMqttTopics(self):        
        print('| Topic | Type | Description | ')
        print('| ----------------------- | ----------- | ---------------------------')
        dev = PCWU(self.conHardId, self.conSoftId, self.devHardId, self.devSoftId, on_message_serial)
        for k, v in dev.registers.items():
            if isinstance(v['name'] , list):
                for i in v['name']:
                    if i:
                        print('| ' + _Device_Pcwu_MqttTopic + '/' + str(i) + ' | ' + v['type'] + ' | ' + str(v.get('desc')))
            else:
                print('| ' +_Device_Pcwu_MqttTopic + '/' + str(v['name'])+ ' | ' + v['type'] + ' | ' + str(v.get('desc')))
            if k > dev.REG_CONFIG_START:          
                print('| ' + _Device_Pcwu_MqttTopic + '/Command/' + str(v['name']) + ' | ' + v.get('type') + ' | ' + str(v.get('desc')))



if __name__ == "__main__":
    # Create an instance of your AppDaemon app
    app = MyApp()
    # Initialize the configuration
    app.initConfiguration()
    # Start MQTT connection
    app.start_mqtt()
    # Add this line to log the MQTT status periodically (e.g., every 60 seconds)
    app.run_every(app.log_mqtt_status, datetime.datetime.now(), 20)
    # Run the AppDaemon app
    app.run()