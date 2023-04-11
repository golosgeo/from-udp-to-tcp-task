import socket
import zlib
import hashlib
import sys
import random
import os
random.seed(5) # randomly generated values for error simulation will always be the same

MY_IP = "127.0.0.2"
RECIEVER_IP = "127.0.0.1"
SENDER_PORT = 5000
RECIEVER_PORT = 8000

FILE = "test.jpg"
FILE_NAME = os.path.join(os.path.dirname(__file__), FILE) # path to the input file
OUTPUT_FILE_NAME = "recv_" + FILE

DATA_LEN = 1000 # length of the piece of data from the file
WIN_SIZE = 8 # number of packets sent at once
TIMEOUT_TIME = 1.0 # timeout time in seconds

# error simulation (can be used as a replacement for netderper)
OUTCOMING_PACKET_LOST_RATE = 0.0 # 0.5 = half of the packets sent are "lost"
INCOMING_PACKET_LOST_RATE = 0.0 # 0.5 = half of received packets "fail to arrive"
# str -> bytes
# int -> bytes
def byteify(data):
	if type(data) == bytes:
		return data
	elif type(data) == str:
		return bytes(data, encoding="utf-8")
	else:
		return bytes(str(data), encoding="utf-8")

# a simple function that calculates how many data packets are needed
def dataPacketCount(ln):
	return ln // DATA_LEN + (ln % DATA_LEN > 0) # round the share up

# socket initialization
def socketInit():
	sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	sock.bind((MY_IP, SENDER_PORT))
	sock.settimeout(TIMEOUT_TIME)
	return sock

# sends packet (from data in bytes format)
def socketSend(sock, data):
	sock.sendto(data,(RECIEVER_IP, RECIEVER_PORT))
	
# packet reception (from any port)
# maximum 1024 bytes
# return content in bytes format
def socketRecv(sock):
	data,address = sock.recvfrom(1024) # address can be discarded
	return data
	
def crc(data): # crc of bytes array
	return zlib.crc32(data)

def sha1(data): # sha1 of the entire contents of the file (bytes format)
	return hashlib.sha1(data).hexdigest()

# central function, waiting for sending to start
# if it finds packet "i", it starts sending again
# if it finds packet "e", it terminates the program
def waitUntilInitSignal(sock):
	print("waiting for signal...")
	while(True):
		try:
			signal = socketRecv(sock)
			if signal == b"i": # reset signal
				print("recieved start/reset signal!")
				break
			elif signal == b'e': # signal to terminate transmission
				print("recieved exit signal!")
				exit(0)
			else:
				print("recieved unknown signal!")
		except KeyboardInterrupt:
			exit(6)
		except SystemExit:
			exit(0)
		except:
			print("signal wait timed out, retrying...")

# return file length, SHA of the file, and data
# data = an array of triple values. Each triple will be the basis for one packet
# triple = (data packet number, DATA_LEN of the data byte from the file, send status)
# the send status is always false at first
def getFileData():
	fp = open(FILE_NAME, "rb")
	fileContent = fp.read()
	
	fileSHA = sha1(fileContent)
	
	fileChunks = [fileContent[i:i+DATA_LEN] for i in range(0, len(fileContent), DATA_LEN)]
	data = [[i, fc, False] for i,fc in enumerate(fileChunks)]
	fp.close()
	return len(fileContent),fileSHA,data

# sends one packet
# packetType = 'l', 'd', ...
# packetNumber = data ('d') packet sequence number, starting from 0. For other packets it has only symbolic meaning
# packetData = array of bytes to send
# crc is not only data, but also packetType and packetNumber
def packetSend(sock, packetType, packetNumber, packetData):
	
	if random.random() < OUTCOMING_PACKET_LOST_RATE:
		print("OUTGOING PACKET LOSS SIMULATED")
		return
	
	# CRC from the rest of the packet!
	packetCRC = crc(byteify(packetType) + byteify(packetNumber) + packetData)
	packetFull = byteify(packetType) + b":" + byteify(packetNumber) + b":" \
			 + byteify(packetCRC) + b":" + packetData
	socketSend(sock, packetFull)
	
# function to receive a single acknowledgement for a specific packet
def singlePacketConf(sock, number): 
	try:
		response = socketRecv(sock)
		
		# if the end packet arrives, stop receiving
		if response == b'e':
			return -4
		
		# confirmation is in the form c:num:crc
		confC,confNumber,confCRC = response.split(b':', 2)
		if confC != b'c':
			# if type ('c') does not match, return None
			print("conf error 1")
			return None
		if byteify(crc(confNumber)) != confCRC:
			# if CRC does not match, return None
			print("conf error 2")
			return None
		if number != int(confNumber) and number != None:
			# if the number does not match the expected number, return None
			# if None is sent as a parameter, it accepts any number
			print("conf error 3")
			return None
		if random.random() < INCOMING_PACKET_LOST_RATE:
			print("INCOMING PACKET LOSS SIMULATED")
			return None
			
		return int(confNumber)
	except KeyboardInterrupt:
		exit(8)
	except:
		# if another error occurs, return None
		print("conf error 4:",sys.exc_info()[0])
		return None

# send packets with name, length and SHA1 code
# retries sending until it receives a correct response
def sendHeaderPackets(sock, fileLen, fileSHA):
	while True:
		print("sending packet n...")
		packetSend(sock, b"n", -3, byteify(OUTPUT_FILE_NAME))
		if singlePacketConf(sock, -3) != None: 
			break
		
	while True:
		print("sending packet l...")
		packetSend(sock, b"l", -2, byteify(fileLen))
		if singlePacketConf(sock, -2) != None:
			break
		
	while True:
		print("sending packet s...")
		packetSend(sock, b"s", -1, byteify(fileSHA))
		if singlePacketConf(sock, -1) != None:
			break

# sends a packet that terminates the transfer
def sendFooterPacket(sock, fileLen):
	while True:
		print("sending packet r...")
		finalPacketNumber = dataPacketCount(fileLen)
		packetSend(sock, b"r", finalPacketNumber, byteify(""))
		if singlePacketConf(sock, finalPacketNumber) != None:
			break

# return the first WIN_SIZE packets (or less) that have not yet been sent
def getFirstNUnsentPackets(fileData):
	dataToSendList = []
	for data in fileData:
		if data[2] == True:
			continue
		if len(dataToSendList) >= WIN_SIZE:
			break
		dataToSendList.append(data)
	return dataToSendList

def sendFileContents(sock, fileData):
	
	while(True):
		print("//new loop iter")
		# find the first WIN_SIZE packets that have not yet been sent
		batchToSend = getFirstNUnsentPackets(fileData)
		
		# if it doesn't find any, it's all done
		if len(batchToSend) == 0:
			print("nothing more to send")
			break
		
		# send them all at once
		for item in batchToSend:
			print("sending packet #", item[0])
			packetSend(sock, b"d", item[0], item[1])
		
		# then receives the same acknowledgement as sent the packet
		# if none arrive, the program simply waits for a timeout
		for i in range(len(batchToSend)):
			responseI = singlePacketConf(sock, None)
			# if a valid packet acknowledgement has arrived, a record that the packet has arrived
			if(responseI != None):
				fileData[responseI][2] = True

sock = socketInit()

while(True):

	# wait for the signal, be on start/reset
	# or for termination
	waitUntilInitSignal(sock)

	fileLen, fileSHA, fileData = getFileData()
	# fileLen = full file char length
	# fileData = file split into sections of 900 chars

	sendHeaderPackets(sock, fileLen, fileSHA)

	sendFileContents(sock, fileData)

	sendFooterPacket(sock, fileLen)
 
	
 