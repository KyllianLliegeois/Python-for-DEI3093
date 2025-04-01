import spidev
import time
import pigpio

# This script is a self test of the chip, no cables appart from the clock (Raspberry clock to JCLK) are needed

# Pi clock generation
pi = pigpio.pi()
pi.set_mode(6, pigpio.ALT0)  # Set GPIO6 to ALT0 for GPCLK0
pi.hardware_clock(6, 2000000)  # Set 1 MHz clock on GPIO6

# SPI setup
spi = spidev.SpiDev()
spi.open(0, 0)  # SPI bus 0, device 0
spi.max_speed_hz = 10000000  # Max SPI speed 10 MHz
spi.mode = 0b00  # SPI Mode 0 (CPOL=0, CPHA=0)

# Function to send SPI command
def send_spi_command(command, data=None):
    if isinstance(data, int):
        # Convert integer to 4-byte list (big endian)
        data = [(data >> 24) & 0xFF, (data >> 16) & 0xFF, (data >> 8) & 0xFF, data & 0xFF]
    elif data is None:
        data = []
    tx_data = [command] + data
    spi.xfer2(tx_data)
    # Just a usual debug thing...
    #print(f"SPI command 0x{command:02X} with data {data} sent")

# Function to receive SPI data in hexadecimal format
def receive_spi_data(command, receive_length):
    rx_data = spi.xfer2([command] + [0x00] * receive_length)
    received_bytes = rx_data[1:]  # Skip the first byte (command echo)
    received_hex = [hex(byte) for byte in received_bytes]
    return received_hex

# 1. Master Reset and FIFO Reset
send_spi_command(0x04)  # Master Reset
send_spi_command(0x44)  # FIFO Reset

# 2. Set ACLK frequency ie: Clock divider, P11 of the Datasheet
send_spi_command(0x38, 0x02)  # ACLK register set to 2
print("ACLK reg:", receive_spi_data(0xD4, 1))

# 3. Configure TX and RX for self-test loopback
send_spi_command(0x08, 0x10)  # TX Control Register: Enable self-test (bit 4)
send_spi_command(0x10, 0x00)  # RX1 Control Register: Set to low speed
send_spi_command(0x24, 0x00)  # RX2 Control Register: Set to low speed

# Verify TX and RX Control Registers, they should match the value set above in section 3
print("TX Control Register:", receive_spi_data(0x84, 1))
print("RX1 Control Register:", receive_spi_data(0x94, 1))
print("RX2 Control Register:", receive_spi_data(0xB4, 1))

# 4. Write ARINC messages to TX FIFO
send_spi_command(0x0C, 0xB0223189)  # Write first ARINC message
send_spi_command(0x0C, 0xB0223189)  # Write second ARINC message

# Check TX Status Register before transmission
print("TX Status Register before TX:", receive_spi_data(0x80, 1)) # Should be at 0 if a message is in queue

# 5. Trigger transmission
print("Triggering transmission...")
send_spi_command(0x40)  # Transmit TX FIFO contents
time.sleep(1)  # Allow time for transmission and loopback

# Check TX and RX Status Registers after transmission
print("TX Status Register after TX:", receive_spi_data(0x80, 1)) # Should be at 1 if all messages are sended
print("RX1 Status Register after TX:", receive_spi_data(0x90, 1)) # Should be at 0 if a message is recieved
print("RX2 Status Register after TX:", receive_spi_data(0xB0, 1)) # Should be at 0 if a message is recieved

# 6. Read back data from RX FIFOs (loopback test)
print("Receiver 1 FIFO Data:", receive_spi_data(0xA0, 4))  # Receiver 1, will print the ARINC message we send
print("Receiver 2 FIFO Data:", receive_spi_data(0xC0, 4))  # Receiver 2

