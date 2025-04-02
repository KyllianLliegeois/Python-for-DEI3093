import spidev
import time
import pigpio

# This file is a more straight forward way to read the output of a arinc device
# I used the A310 ARINC label and encoding (significants bits) , fell free to adapt but they should be standard (for label at least) even for 320 or Boeing
# Functions are reused from the self test of the chip detailed in /test/

data_processed_old = 0

pi = pigpio.pi()
pi.set_mode(6, pigpio.ALT0)  # Set GPIO6 to ALT0 for GPCLK0
pi.hardware_clock(6, 2000000)  # Set 2 MHz clock on GPIO6

# SPI setup
spi = spidev.SpiDev()
spi.open(0, 0)  # SPI bus 0, device 0
spi.max_speed_hz = 10000000  # Max SPI speed 10 MHz
spi.mode = 0b00  # SPI Mode 0 (CPOL=0, CPHA=0)

def spi_init():


    #HARDWARE SETUP
    # 1. Master Reset and FIFO Reset
    send_spi_command(0x04)  # Master Reset
    send_spi_command(0x44)  # FIFO Reset

    # 2. Set ACLK frequency
    send_spi_command(0x38, 0x02)  # ACLK register set to 2 (adjust as needed)
    print("ACLK reg:", receive_spi_data(0xD4, 1))

    # 3. Configure TX and RX
    send_spi_command(0x08, 0x01)  # TX Control Register: Enable self-test (bit 4), low speed bit 1
    send_spi_command(0x10, 0x01)  # RX1 Control Register
    send_spi_command(0x24, 0x01)  # RX2 Control Register: Set to low speed


# Function to send SPI command
def send_spi_command(command, data=None):
    if isinstance(data, int):
        # Convert integer to 4-byte list (big endian)
        data = [(data >> 24) & 0xFF, (data >> 16) & 0xFF, (data >> 8) & 0xFF, data & 0xFF]
    elif data is None:
        data = []
    tx_data = [command] + data
    spi.xfer2(tx_data)
    print(f"SPI command 0x{command:02X} with data {data} sent")

# Function to receive SPI data in hexadecimal format
def receive_spi_data(command, receive_length):
    rx_data = spi.xfer2([command] + [0x00] * receive_length)
    received_bytes = rx_data[1:]  # Skip the first byte (command echo)
    received_hex = [hex(byte) for byte in received_bytes]
    return received_hex

def binary_from_hex(hex_values):
    """
    Reverses the binary representation of a list of hexadecimal values.

    :param hex_values: List of hexadecimal values as strings (e.g., ['0x7f', '0xff', '0x30', '0x17'])
    :return: The reversed binary string and the octal representation of its first 8 bits.
    """
    # Step 1: Convert hex to binary and pad to 8 bits
    binary_string = ''.join(f"{int(h, 16):08b}" for h in hex_values)
    
    last_8_bits = binary_string[24:32]
    #print(last_8_bits)
    # Step 2: Reverse the binary string
    label = last_8_bits[::-1]
    label = f"{int(label, 2):o}"

    return binary_string,label

def decode_word(hex_values):

    # convert raw hex message from fifo to binary (easier to manipulate for my smooth brain)
    arinc_message_binary = ''.join(f"{int(h, 16):08b}" for h in hex_values)

    # extract the label, reverse it (cause the label is inverted in arinc) and converting it to octal
    label_bits = arinc_message_binary[24:32]
    label = label_bits[::-1]
    label_octal = f"{int(label, 2):o}"

    sdi = arinc_message_binary[22:23]
    
    payload = arinc_message_binary[4:22]

    ssm = arinc_message_binary[1:3]

    parity=  arinc_message_binary[0:1]

    return label_octal,sdi,payload,ssm,parity,arinc_message_binary

def decode_altitude(payload):
    # Label 102, alt in ft, 16 signifiant bits
    altitude = payload[0:16]
    altitude = int(altitude,2)
    return altitude

def decode_speed(payload):
    # Label 103, speed in knots unless mach engage (not same label), but WHY THE FUCK is there 9 real sig bit and 11 specified in AMM ???

    speed = payload[0:9]
    speed = int(speed,2)
    return speed

def decode_hdg(payload):
    #label 101 + or - 180 coded on 12 bits, and yeah it's the heading
    # Ok the non BCD label is encoded idk how so let's switch to bcd one (026)

    last_digit = int(payload[6:10],2)
    middle_digit = int(payload[2:6],2)
    first_digit = int(payload[0:2],2)

    hdg = first_digit * 100 + middle_digit * 10 + last_digit

    return hdg

def decode_vertical_speed(payload):
    #label 104, well just the V/S. Can't recieve any data, it is maybe dependant of the FCC broadcast ?

    vs = payload

    return vs

def decode_discrete_word_1(payload):
    #label 104, well just the V/S. Can't recieve any data, it is maybe dependant of the FCC broadcast ?

    word = payload

    return word


#MAIN SECTION
#f = open("ArincLog.txt", "a")
#print("Reading input... File will be saved as ArincLog.txt")

def reading():
    spi_init()
    while 1 == 1:

        data_recieved = receive_spi_data(0xA0, 4)
        #print(data_recieved)
        data_decoded = decode_word(data_recieved)

        label = int(data_decoded[0])

        match label:

            case 102:
                altitude = decode_altitude(data_decoded[2])
                print("Altitude : ",altitude)
        
            case 103:
                speed = decode_speed(data_decoded[2])
                print("Speed : ",speed)

            case 23:
                hdg = decode_hdg(data_decoded[2])
                print("Heading : ",hdg)
        
            case 104:
                vertical_speed = decode_vertical_speed(data_decoded[2])
                #print(vertical_speed)
            case 271:
                word_1 = decode_discrete_word_1(data_decoded[2])
                #print(word_1)
        

        time.sleep(0.24)


def encode_word(label_octal, sdi, payload, ssm, parity):
    """
    Encodes ARINC components into a 32-bit ARINC word.

    :param label_octal: Label in octal (e.g., "377").
    :param sdi: Source/Destination Identifier (1 bit, as string).
    :param payload: 18-bit payload data (binary string).
    :param ssm: Sign/Status Matrix (2 bits, as string).
    :param parity: Parity bit (1 bit, as string).
    :return: Hexadecimal representation of the encoded ARINC word.
    """
    # Convert label from octal to binary and reverse it
    label_decimal = int(label_octal, 8)
    label_bits = f"{label_decimal:08b}"[::-1]  # Reverse the bits
    
    # Ensure all fields have correct lengths
    sdi = f"{int(sdi, 2):02b}"  # SDI should be 2 bits
    payload = f"{int(payload, 2):018b}"  # Payload should be 18 bits
    ssm = f"{int(ssm, 2):02b}"  # SSM should be 2 bits
    parity = f"{int(parity, 2):01b}"  # Parity should be 1 bit
    
    # Combine all fields into a single binary string
    arinc_message_binary = parity + ssm + payload + sdi + label_bits

    # Convert binary to hexadecimal values (8-bit chunks)
    hex_values = [f"0x{int(arinc_message_binary[i:i+8], 2):02X}" for i in range(0, 32, 8)]

    return hex_values, arinc_message_binary

def send_arinc(arinc_hex):
    send_spi_command(0x0c,arinc_hex)
    send_spi_command(0x40)
    
