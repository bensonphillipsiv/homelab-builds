import os, struct, socket
from dotenv import load_dotenv
import opuslib


load_dotenv()
AUDIO_DEVICE_IP = os.getenv("AUDIO_DEVICE_IP")
LOCAL_IP = "0.0.0.0"
RECV_PORT = 5004
SEND_PORT = 5005

# Audio format
CHANNELS = 1
SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2  # s16le (16-bit)

# Frame sizing
SAMPLES_PER_20MS = SAMPLE_RATE // 50               # 320 samples @ 20 ms
BYTES_PER_20MS   = SAMPLES_PER_20MS * BYTES_PER_SAMPLE * CHANNELS  # 640 bytes

# RTP / Opus specifics
RTP_CLOCK_RATE       = 48000                       # Opus RTP clock is always 48 kHz (RFC 7587)
RTP_TICKS_PER_20MS   = RTP_CLOCK_RATE // 50        # 960 ticks per 20 ms
PAYLOAD_TYPE         = 111                          


class BidirectionalRTPHandler: 
    def __init__(self, pi_ip=AUDIO_DEVICE_IP, recv_port=RECV_PORT, send_port=SEND_PORT):
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
    
    # def create_rtp_header(self):
    #     """Create RTP header for outgoing packets"""
    #     header = struct.pack('!BBHII',
    #         0x80,  # V=2, P=0, X=0, CC=0
    #         111,   # PT=111 (Opus)
    #         self.seq_num,
    #         self.timestamp,
    #         self.ssrc
    #     )
    #     self.seq_num = (self.seq_num + 1) & 0xFFFF
    #     self.timestamp += SAMPLES_PER_20MS
    #     return header
    
    def create_rtp_header(self, marker: bool = False) -> bytes:
        """
        Minimal RTP header for Opus:
        - Version=2, P=0, X=0, CC=0
        - M=marker (start of talkspurt), PT=self.payload_type (e.g., 111)
        - seq, timestamp (48 kHz clock), ssrc
        """
        b0 = 0x80  # V=2, P=0, X=0, CC=0
        b1 = (0x80 if marker else 0x00) | (self.payload_type & 0x7F)
        return struct.pack("!BBHII", b0, b1, self.seq, self.ts, self.ssrc)
        
    def send_audio(self, pcm_data: bytes, end: bool = False):
        """
        Accept an arbitrary-length PCM s16le mono@16k block and send as 20 ms Opus/RTP.
        - Buffers partial frames between calls
        - Uses RTP marker bit on first packet of each talkspurt
        - Increments RTP seq/timestamp correctly for Opus (48kHz clock)
        Args:
            pcm_data: raw PCM s16le mono at 16 kHz
            end: if True, flush (pad) any trailing partial frame and mark next packet as new talkspurt
        """
        # Lazy-init sender state
        if not hasattr(self, "send_buffer"):
            self.send_buffer = bytearray()
        if not hasattr(self, "seq"):
            import os, random
            self.seq = random.randrange(0, 1 << 16)
            self.ts = random.randrange(0, 1 << 32)
            self.ssrc = int.from_bytes(os.urandom(4), "big")
            self.payload_type = getattr(self, "payload_type", PAYLOAD_TYPE)
            self.marker_next = True  # set marker on first packet of a talkspurt

        # Append new data
        if pcm_data:
            self.send_buffer.extend(pcm_data)

        # Emit complete 20 ms frames
        while len(self.send_buffer) >= BYTES_PER_20MS:
            frame = bytes(self.send_buffer[:BYTES_PER_20MS])
            del self.send_buffer[:BYTES_PER_20MS]

            # Encode one 20ms frame. Most Opus encoders take s16le bytes + frame size in samples.
            opus_frame = self.encoder.encode(frame, SAMPLES_PER_20MS)

            # Build RTP header (marker set only on first packet of a talkspurt)
            rtp_hdr = self.create_rtp_header(marker=self.marker_next)
            self.marker_next = False  # only first packet gets marker

            # Send
            self.send_sock.sendto(rtp_hdr + opus_frame, self.pi_addr)

            # Advance RTP state
            self.seq = (self.seq + 1) & 0xFFFF
            self.ts = (self.ts + RTP_TICKS_PER_20MS) & 0xFFFFFFFF
            
        
    def flush_audio(self):
        """Send any remaining buffered audio (padded with silence)"""
        if hasattr(self, 'send_buffer') and self.send_buffer:
            BYTES_PER_20MS = SAMPLES_PER_20MS * 2
            remaining = bytes(self.send_buffer)
            if len(remaining) < BYTES_PER_20MS:
                remaining += b'\x00' * (BYTES_PER_20MS - len(remaining))
            self.send_buffer.clear()
            
            opus_frame = self.encoder.encode(remaining, SAMPLES_PER_20MS)
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
