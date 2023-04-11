import os
import socket
import zlib
import hashlib
import sys
import random
random.seed(7) # randomly generated values for error simulation will always be the same

MY_IP = "127.0.0.1"
SENDER_IP = "127.0.0.2"
SENDER_PORT = 5000 
RECIEVER_PORT = 8000

DATA_LEN = 1000 # length of the piece of data from the file

# error simulation (can be used as a replacement for netderper)
WRONG_SHA_RATE = 0.0 # 0.5 = half of the SHA values will be marked as bad

# str -> bytes
# int -> bytes
def byteify(data):
	if type(data) == bytes:
		return data
	elif type(data) == str:
		return bytes(data, encoding="utf-8")
	else:
		return bytes(str(data), encoding="utf-8")

# function calculates how many data packets are needed
def dataPacketCount(ln):
	return ln // DATA_LEN + (ln % DATA_LEN > 0) # rounded the division up

# socket initialization
def socketInit():
	sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	sock.bind((MY_IP, RECIEVER_PORT))
	sock.settimeout(3600) # timeout 1 hour. No need to limit anything
	return sock

# sends packet (from data in bytes format)
def socketSend(sock, data):
	sock.sendto(data,(SENDER_IP, SENDER_PORT))

# packet reception (from any port)
# maximum 1024 bytes
# return content in bytes format
def socketRecv(sock):
	data,address = sock.recvfrom(1024) # address lze zahodit
	return data

# function to be run after the transfer is completed
# if any transmission is still in progress on the sender side, it will send packets until it is finished
def ensureCommunicationEnd(sock):
	# possibly sleep here?
	sock.settimeout(10)
	while(True):
		# if there is still a packet sent, socketRecv will NOT throw an error
		try:
			data = socketRecv(sock)
		except:
			return
		socketSend(sock, b"e")

def crc(data): # crc of bytes array
	return zlib.crc32(data)

def sha1(data): # sha1 of the entire contents of the file (bytes format)
	return hashlib.sha1(data).hexdigest()

# waiting for packet, no timeout
# CRC is calculated from char + number + data [!]
# correct CRC -> send c:confnum:crc
# wrong CRC -> does nothing, waits for timeout
def packetRecv(sock):
	try:
		packetRaw = socketRecv(sock) # x:num:crc:data
		packetChar,packetNumB,packetCRC,packetData = packetRaw.split(b':',3)
		
		if byteify(crc(packetChar+packetNumB+packetData)) != packetCRC:
			print("obtained wrong packet CRC!")
			return None
		
		# if the program got here, the correct packet arrived
		
		# send confirmation
		confirmation = b"c:" + byteify(packetNumB) + b":" + byteify(crc(packetNumB))
		socketSend(sock, confirmation)
		
		return packetChar, int(packetNumB), packetData
	except KeyboardInterrupt:
		exit(5)
	except:
		print("packet recv error:", sys.exc_info()[0])
		return None


sock = socketInit()

while(True):
	# initialization of variables
	file_name = None # file name
	file_len = None # file length in bytes
	file_packetCount = None # packet count
	file_segmentList = None # array of bytes for each packet
	file_packetConfirmedList = None # packet acknowledgement field
	file_sha = None # sha file code (string)

	# signal to start transmission
	# so the receiver starts the transfer and therefore the sender must be enabled drive
	print("sending init signal...")
	socketSend(sock, b"i")

	print("Starting main recv loop...")

	# main cycle
	while(True):
		# gets packet
		packetData = packetRecv(sock)
		
		# if the function returned None, it means that the packet content was corrupted
		# if this happens, the program simply ignores the packet and tries to receive another one
		if packetData == None:
			print("recieved wrong packet data, going for new recieve")
			continue
		
		# if the packet is cool, it will load the data from it
		# type, sequence number, content
		packetChar, packetNum, packetData = packetData
		
		# n = packet with filename
		# convert the packet content to string and save
		if packetChar == b'n':
			print("got packet type n")
			file_name = os.path.join(os.path.dirname(__file__), "test.jpg")
   
		# l = packet with file length
		# string array length = packet count = (file length / DATA_LEN) rounded up
		elif packetChar == b'l':
			print("got packet type l")
			file_len = int(packetData)
			file_packetCount = dataPacketCount(file_len)
			file_segmentList = [""]*file_packetCount
			file_packetConfirmedList = [False]*file_packetCount
			print("--will use",file_packetCount,"packets")
		
		# s = packet with SHA code
		# if it has already received SHA, probably the last acknowledgement was lost - simply overwrite the variable again, it doesn't matter
		elif packetChar == b's':
			print("got packet type s")
			file_sha = packetData
			
		# d = packet with file content
		# save the contents to the appropriate place in the string array
		# record that it was received correctly - redundant for now
		elif packetChar == b'd':
			# packetNum = 0...filepacketcount
			# packetData = až 900 znaků dat
			print("got packet type d, #", packetNum)
			
			file_segmentList[packetNum] = packetData
			
			file_packetConfirmedList[packetNum] = True
		
		# r = last packet to confirm that the file was sent in full
		elif packetChar == b'r':
			print("got packet type r")
			print("recieved last packet, saving file...")
			break

	# sometimes throws typeError instead of exit - so exit manually
	# you might want to fix this somehow
	try:
		file_bytes = b''.join(file_segmentList) # spoj data ze vsech packetu
	except TypeError:
		continue
	
	# finally check if the SHA values are the same
	# if so, sends an 'e' packet to terminate the transfer
	if file_sha == byteify(sha1(file_bytes)) and random.random() >= WRONG_SHA_RATE:
		print("sha1 codes equal, exiting...")
		socketSend(sock, b"e")
		break
	else:
		print("sha1 codes NOT equal! Resetting...")
		

# saving at the end
print("saving file to", file_name)
with open(file_name, 'wb') as f:
	f.write(file_bytes)


# additionally check if the transfer has been completed correctly
ensureCommunicationEnd(sock)

sock.close()
