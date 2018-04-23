#!/usr/bin/env python
"""
	*
	* Project Name: 	Eclassroom
	* Author List: 		NIkhil Vatwani,Vijay Kataria
	* Filename: 		snoboydecoder.py
	* Functions: 		 play_audio_file,start,saveMessage,terminate
	* Global Variables:	 interrupted,logger,RESOURCE_FILE,DETECT_sDING
	*
	
"""
import collections
import pyaudio
import snowboydetect
import time
import wave
import os
import logging

logging.basicConfig()
logger = logging.getLogger("snowboy")
logger.setLevel(logging.INFO)
TOP_DIR = os.path.dirname(os.path.abspath(__file__))

RESOURCE_FILE = os.path.join(TOP_DIR, "resources/common.res")
DETECT_DING = os.path.join(TOP_DIR, "resources/ding.wav")
DETECT_DONG = os.path.join(TOP_DIR, "resources/dong.wav")


class RingBuffer(object):
    """Ring buffer to hold audio from PortAudio"""
    def __init__(self, size = 4096):
        self._buf = collections.deque(maxlen=size)

    def extend(self, data):
        """Adds data to the end of buffer"""
        self._buf.extend(data)

    def get(self):
        """Retrieves data from the beginning of buffer and clears it"""
        tmp = bytes(bytearray(self._buf))
        self._buf.clear()
        return tmp

""""
	* Function Name:	play_audio_file
	* Input:		fname(wav audiofile name)
	* Output:		None
	* Logic:		Simple callback function to play a wave file. By default it plays a Ding sound.
	* Example Call:		play_audio_file 
	*
"""
def play_audio_file(fname=DETECT_DING):
    ding_wav = wave.open(fname, 'rb')
    ding_data = ding_wav.readframes(ding_wav.getnframes())
    audio = pyaudio.PyAudio()
    stream_out = audio.open(
        format=audio.get_format_from_width(ding_wav.getsampwidth()),
        channels=ding_wav.getnchannels(),
        rate=ding_wav.getframerate(), input=False, output=True)
    stream_out.start_stream()
    stream_out.write(ding_data)
    time.sleep(0.2)
    stream_out.stop_stream()
    stream_out.close()
    audio.terminate()


class HotwordDetector(object):
    """
    Snowboy decoder to detect whether a keyword specified by `decoder_model`
    exists in a microphone input stream.
    :param decoder_model: decoder model file path, a string or a list of strings
    :param resource: resource file path.
    :param sensitivity: decoder sensitivity, a float of a list of floats.
                              The bigger the value, the more senstive the
                              decoder. If an empty list is provided, then the
                              default sensitivity in the model will be used.
    :param audio_gain: multiply input volume by this factor.
    """
    def __init__(self, decoder_model,
                 resource=RESOURCE_FILE,
                 sensitivity=[],
                 audio_gain=1):

        def audio_callback(in_data, frame_count, time_info, status):
            self.ring_buffer.extend(in_data)
            play_data = chr(0) * len(in_data)
            return play_data, pyaudio.paContinue

        tm = type(decoder_model)
        ts = type(sensitivity)
        if tm is not list:
            decoder_model = [decoder_model]
        if ts is not list:
            sensitivity = [sensitivity]
        model_str = ",".join(decoder_model)

        self.detector = snowboydetect.SnowboyDetect(
            resource_filename=resource.encode(), model_str=model_str.encode())
        self.detector.SetAudioGain(audio_gain)
        self.num_hotwords = self.detector.NumHotwords()

        if len(decoder_model) > 1 and len(sensitivity) == 1:
            sensitivity = sensitivity*self.num_hotwords
        if len(sensitivity) != 0:
            assert self.num_hotwords == len(sensitivity), \
                "number of hotwords in decoder_model (%d) and sensitivity " \
                "(%d) does not match" % (self.num_hotwords, len(sensitivity))
        sensitivity_str = ",".join([str(t) for t in sensitivity])
        if len(sensitivity) != 0:
            self.detector.SetSensitivity(sensitivity_str.encode())

        self.ring_buffer = RingBuffer(
            self.detector.NumChannels() * self.detector.SampleRate() * 5)
        self.audio = pyaudio.PyAudio()
        self.stream_in = self.audio.open(
            input=True, output=False,
            format=self.audio.get_format_from_width(
                self.detector.BitsPerSample() / 8),
            channels=self.detector.NumChannels(),
            rate=self.detector.SampleRate(),
            frames_per_buffer=2048,
            stream_callback=audio_callback)

""""
	* Function Name:	start
	* Input:		:param detected_callback: a function or list of functions. The number of
                                  items must match the number of models in
                                  `decoder_model`,
                                 interrupt_check: a function that returns True if the main loop needs to stop.
                                :param float sleep_time: how much time in second every loop waits.
                                :param audio_recorder_callback: if specified, this will be called after
                                 a keyword has been spoken and after the phrase immediately after the keyword
                                 has been recorded. The function will be passed the name of the file where the
                                 phrase was recorded.
                                :param silent_count_threshold: indicates how long silence must be heard
                                 to mark the end of a phrase that is being recorded.
                                :param recording_timeout: limits the maximum length of a recording.

	*return :		None
	* Logic:		 Start the voice detector. For every `sleep_time` second it checks the
                                audio buffer for triggering keywords. If detected, then call corresponding
                                function in `detected_callback`, which can be a single function (single model)
                                or a list of callback functions (multiple models). Every loop it also calls
                                `interrupt_check` -- if it returns True, then breaks from the loop and return.
       
	* Example Call:		detector.start(conn,detected_callback=detectedCallback,
                                audio_recorder_callback=audioRecorderCallback,
                              interrupt_check=interrupt_callback,
                               sleep_time=0.01)
 
"""
    def start(self, conn,detected_callback=play_audio_file,
              interrupt_check=lambda: False,
              sleep_time=0.03,
              audio_recorder_callback=None,
              silent_count_threshold=15,
              recording_timeout=10):
        
        if interrupt_check():
            logger.debug("detect voice return")
            return

        tc = type(detected_callback)
        if tc is not list:
            detected_callback = [detected_callback]
        if len(detected_callback) == 1 and self.num_hotwords > 1:
            detected_callback *= self.num_hotwords

        assert self.num_hotwords == len(detected_callback), \
            "Error: hotwords in your models (%d) do not match the number of " \
            "callbacks (%d)" % (self.num_hotwords, len(detected_callback))

        logger.debug("detecting...")

        state = "PASSIVE"
        while True:
            if interrupt_check():
                logger.debug("detect voice break")
                break
            data = self.ring_buffer.get()
            if len(data) == 0:
                time.sleep(sleep_time)
                continue

            status = self.detector.RunDetection(data)
            if status == -1:
                logger.warning("Error initializing streams or reading audio data")

            #small state machine to handle recording of phrase after keyword
            if state == "PASSIVE":
                if status > 0: #key word found
                    self.recordedData = []
                    self.recordedData.append(data)
                    silentCount = 0
                    recordingCount = 0
                    message = "Keyword " + str(status) + " detected at time: "
                    message += time.strftime("%Y-%m-%d %H:%M:%S",
                                         time.localtime(time.time()))
                    logger.info(message)
                    callback = detected_callback[status-1]
                    if callback is not None:
                        callback()
                    conn.send(str(status))
                    if status == 3:
                        print("picture taken")
                    if audio_recorder_callback is not None:
                        if status == 4:
                            state = "ACTIVE"
                        elif status == 5:
                            state = "ACTIVE"
                        elif status == 8:
                            state = "ACTIVE"
                        
                        
                    continue

            elif state == "ACTIVE":
                stopRecording = False
                if recordingCount > recording_timeout:
                    stopRecording = True
                elif status == -2: #silence found
                    if silentCount > silent_count_threshold:
                        stopRecording = True
                    else:
                        silentCount = silentCount + 1
                elif status == 0: #voice found
                    silentCount = 0

                if stopRecording == True:
                    fname = self.saveMessage()
                    audio_recorder_callback(fname)
                    state = "PASSIVE"
                    continue

                recordingCount = recordingCount + 1
                self.recordedData.append(data)

        logger.debug("finished.")
""""
	* Function Name:	saveMessage
	* Input:                self.recordedData(object.recordedData)
	* Output:		saves the message stored in self.recordedData(object.recordedData) to a timestamped file
	* Logic:		uses Wav to save data
	* Example Call:		Called after self.saveMessage()
	*
"""

    def saveMessage(self):
        
        filename = 'output' + str(int(time.time())) + '.wav'
        data = b''.join(self.recordedData)
        wf = wave.open(filename, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(self.audio.get_sample_size(
            self.audio.get_format_from_width(
                self.detector.BitsPerSample() / 8)))
        wf.setframerate(self.detector.SampleRate())
        wf.writeframes(data)
        wf.close()
        logger.debug("finished saving: " + filename)
        return filename
""""
	* Function Name:	terminate
	* Input:                self(instance)
	* Logic:		Terminate audio stream. Users cannot call start() again to detect.
                                :return: None
	* Example Call:		audio.terminate() where audio =pyaudio.PyAudio()
	*
"""
    def terminate(self):
        """
       
        """
        self.stream_in.stop_stream()
        self.stream_in.close()
        self.audio.terminate()