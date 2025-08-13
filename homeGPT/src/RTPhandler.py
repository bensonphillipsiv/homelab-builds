import os, struct, socket
from dotenv import load_dotenv
import opuslib


load_dotenv()
LOCAL_IP = "192.168.1.141"
PI_IP = "192.168.1.131"  # Add your Pi's IP here
RECV_PORT = 5004  # Port for receiving from Pi (mic audio)
SEND_PORT = 5005  # Port for sending to Pi (TTS/responses)

CHANNELS = 1
SAMPLE_RATE = 16000
FRAME_BYTES = 2 * CHANNELS
SAMPLES_PER_80MS = SAMPLE_RATE * 80 // 1000  # 1280 samples @ 80ms
SAMPLES_PER_20MS = SAMPLE_RATE * 20 // 1000  # 320 samples @ 20ms


class BidirectionalRTPHandler:
    def __init__(self, pi_ip=PI_IP, recv_port=RECV_PORT, send_port=SEND_PORT):
        # Receiving setup (from Pi microphone)
        self.decoder = opuslib.Decoder(SAMPLE_RATE, CHANNELS)
        self.recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.recv_sock.bind((LOCAL_IP, recv_port))
        
        # Sending setup (to Pi speakers)
        self.encoder = opuslib.Encoder(SAMPLE_RATE, CHANNELS, opuslib.APPLICATION_VOIP)
        self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.pi_addr = (pi_ip, send_port)
        
        # RTP state for sending
        self.seq_num = 0
        self.timestamp = 0
        self.ssrc = 12345
        
        self.frame_buffer = []  # Buffer to accumulate 20ms frames into 80ms
        print(f"Listening on {LOCAL_IP}:{recv_port}, sending to {pi_ip}:{send_port}")
    
    def create_rtp_header(self):
        """Create RTP header for outgoing packets"""
        header = struct.pack('!BBHII',
            0x80,  # V=2, P=0, X=0, CC=0
            111,   # PT=111 (Opus)
            self.seq_num,
            self.timestamp,
            self.ssrc
        )
        self.seq_num = (self.seq_num + 1) & 0xFFFF
        self.timestamp += SAMPLES_PER_20MS
        return header
    
    def send_audio(self, pcm_data):
        """Send PCM audio to Pi speakers (for TTS playback)"""
        # Ensure pcm_data is the right size (20ms chunks)
        if len(pcm_data) == SAMPLES_PER_20MS * 2:  # 640 bytes for 20ms
            opus_frame = self.encoder.encode(pcm_data, SAMPLES_PER_20MS)
            rtp_packet = self.create_rtp_header() + opus_frame
            self.send_sock.sendto(rtp_packet, self.pi_addr)
        else:
            # If not 20ms, chunk it
            for i in range(0, len(pcm_data), SAMPLES_PER_20MS * 2):
                chunk = pcm_data[i:i + SAMPLES_PER_20MS * 2]
                if len(chunk) == SAMPLES_PER_20MS * 2:
                    opus_frame = self.encoder.encode(chunk, SAMPLES_PER_20MS)
                    rtp_packet = self.create_rtp_header() + opus_frame
                    self.send_sock.sendto(rtp_packet, self.pi_addr)
    
    def get_audio_data(self):
        """Generator that yields decoded PCM audio data from Pi mic"""
        while True:
            try:
                # Receive packet
                data, addr = self.recv_sock.recvfrom(2048)
                
                # Skip RTP header (12 bytes minimum)
                if len(data) > 12:
                    opus_payload = data[12:]  # Simple header skip
                    
                    # Decode Opus to PCM (20ms frame = 320 samples)
                    pcm_data = self.decoder.decode(opus_payload, SAMPLES_PER_20MS)
                    yield pcm_data
                    
            except Exception as e:
                print(f"Error: {e}")
                continue
    
    def get_80ms_frames(self):
        """Buffer 20ms frames and yield 80ms frames for wake word detection"""
        for pcm_20ms in self.get_audio_data():
            self.frame_buffer.append(pcm_20ms)
            
            # When we have 4 x 20ms frames, combine into 80ms frame
            if len(self.frame_buffer) >= 4:
                # Combine 4 frames into one 80ms frame
                combined_pcm = b''.join(self.frame_buffer[:4])
                self.frame_buffer = self.frame_buffer[4:]  # Remove used frames
                yield combined_pcm
    
    def close(self):
        self.recv_sock.close()
        self.send_sock.close()
