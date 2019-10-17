import os, sys, time, wx, threading
from array import array
import pyaudio
import wave
# The recommended way to use wx with mpl is with the WXAgg backend.
import matplotlib
matplotlib.use('WXAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import \
	FigureCanvasWxAgg as FigCanvas, \
	NavigationToolbar2WxAgg as NavigationToolbar
import numpy as np
import pylab
from datetime import date, datetime

import about

EVT_RESULT_ID = wx.NewId()

def EVT_RESULT(win, func):
	win.Connect(-1, -1, EVT_RESULT_ID, func)

class ResultEvent(wx.PyEvent):
	def __init__(self, data):
		wx.PyEvent.__init__(self)
		self.SetEventType(EVT_RESULT_ID)
		self.data = data

class WorkerThread(threading.Thread):
	chunk = 1024
	format = pyaudio.paInt16
	channels = 2
	rate = 44100

	def __init__(self, notify_window):
		threading.Thread.__init__(self)
		self._notify_window = notify_window
		
		self.p = pyaudio.PyAudio()
		self.max = 32766
		self.frames = []
		
		self.stream = self.p.open(format=self.format,
			channels=self.channels,
			rate=self.rate,
			input=True,
			frames_per_buffer=self.chunk)
		
		#This system is to ensure that the thread is not stopped in the middle of a stream read operation. It must wait until the read is complete, to avoid hanging
		self.prepareToTerminate = False
		self.terminate = False
		self.prepareToPause = False
		self.pausedState = False
		self.start()

	def run(self):
		while True:
			if self.prepareToTerminate:
				self.terminate = True
				
				self.stream.stop_stream()
				self.stream.close()
				self.p.terminate()
				
				break
			elif self.pausedState:
				continue
			elif self.prepareToPause:
				self.prepareToPause = False
				self.pausedState = True
				self.stream.stop_stream()
				
				continue
			
			data = self.stream.read(self.chunk)
			x = max(array('h',data))
			self.frames.append(data)
			
			y = x / float(self.max)
			
			#This was an experimental feature to adjust the height of the graph. It effectively limits the display to make volume changes easier to see
			cap = None
			if cap:
				y /= cap
			y = min(0.99, y) * 100.0
			if not self.terminate:
				if self._notify_window.__class__ != wx._core._wxPyDeadObject:
					wx.PostEvent(self._notify_window, ResultEvent(y))

	def abort(self):
		self.prepareToTerminate = True

	def pause(self):
		self.prepareToPause = True

	def resume(self):
		self.stream.start_stream()
		
		self.pausedState = False

	def export(self, filepath):
		self.trim()
		
		localPath = sys.path[0].replace('/lib/python'+str(sys.version_info.major)+str(sys.version_info.minor)+'.zip','')
		savePath = os.path.join(localPath, 'recording.wav')
		
		saveToiTunes = filepath is None
		if saveToiTunes:
			t = date.today()
			x = datetime.now()
			
			timeString = str(t.year)+'.'+str(t.month).zfill(2)+'.'+str(t.day).zfill(2)+' '+('PM' if x.hour > 11 else 'AM')+' Recording'
			
			desktopPath = os.path.expanduser('~/Desktop')
			filepath = os.path.join(desktopPath, timeString+'.m4a')
			if os.path.exists(filepath):
				i = 0
				while os.path.exists(filepath):
					i += 1
					
					filepath = os.path.join(desktopPath, timeString+'_'+str(i)+'.m4a')
		
		#Save the recording as a wav
		wf = wave.open(savePath, 'wb')
		wf.setnchannels(self.channels)
		wf.setsampwidth(self.p.get_sample_size(self.format))
		wf.setframerate(self.rate)
		wf.writeframes(b''.join(self.frames))
		wf.close()
		
		#Convert the wav to m4a
		saved = False
		if os.path.exists(savePath):
			os.system("afconvert -d alac "+savePath.replace(' ',"\ ")+" "+filepath.replace(' ',"\ "))
			os.remove(savePath)
			if os.path.exists(filepath):
				saved = True
		if not saved:
			wx.MessageBox('There was a problem.', 'Error', wx.OK | wx.ICON_ERROR)
			return
		
		if saveToiTunes:
			applicationName = "Music" if int(os.uname().release.split('.')[0]) > 18 else "iTunes"
			os.system('open '+filepath.replace(' ',"\ ")+'; osascript -e "on appIsRunning(appName)" -e "tell application \\"System Events\\" to (name of processes) contains appName" -e "end appIsRunning" -e "if appIsRunning(\\"'+applicationName+'\\") then" -e "tell application \\"'+applicationName+'\\" to pause" -e "end if"')
		else:
			wx.MessageBox('File saved successfully.', 'Saved', wx.OK | wx.ICON_INFORMATION)
		
		#Clear the recording now that it has been saved
		del self.frames[:]
		return True

	#Trim
	def _trim(self, snd_data):
		threshold = 800
		
		snd_started = False
		r = []
		
		for i in snd_data:
			if not snd_started and max(array('h',i)) > threshold:
				snd_started = True
				r.append(i)
			elif snd_started:
				r.append(i)
		return r

	def trim(self):
		snd_data = self._trim(self.frames)
		snd_data.reverse()
		snd_data = self._trim(snd_data)
		snd_data.reverse()
		self.frames = snd_data

class ListenFrame(wx.Frame):
	title = 'Listen'
	
	def __init__(self):
		wx.Frame.__init__(self, None, wx.ID_ANY, self.title, style=wx.MINIMIZE_BOX | wx.SYSTEM_MENU | wx.CAPTION | wx.CLOSE_BOX | wx.CLIP_CHILDREN)
		self.SetSize((488,422))
		self.Centre()
		
		self.Bind(wx.EVT_CLOSE, self.on_exit)
		self.Bind(wx.EVT_MENU, self.on_exit, id=wx.ID_EXIT)
		
		self.data = []
		self.lastDatum = None
		self.paused = True
		
		self.newVolume = None
		
		self.create_menu()
		self.create_main_panel()
		
		self.redraw_timer = wx.Timer(self)
		self.Bind(wx.EVT_TIMER, self.on_redraw_timer, self.redraw_timer)		
		self.redraw_timer.Start(50)
		
		EVT_RESULT(self,self.OnResult)
		
		self.worker = None
		
		self.timeStarted = None
		self.existingDuration = 0
		
		self.Bind(wx.EVT_CHAR_HOOK, self.onKeyPress)

	def onKeyPress(self, event):
		keycode = event.GetKeyCode()
		if keycode == 32:
			#Space
			self.on_pause_button(None)
		elif keycode == 61 or keycode == 45:
			#Plus or minus
			value = self.slider.GetValue()
			if keycode == 61:
				value += 5
			else:
				value -= 5
			self.slider.SetValue(value)
			
			self.onInputSliderChange(None)
		else:
			event.Skip()

	#Menu
	def about(self, event):
		about.About()

	def create_menu(self):
		self.menubar = wx.MenuBar()
		
		menu_file = wx.Menu()
		clearItem = menu_file.Append(wx.ID_ANY, "&Clear\tEsc")
		self.Bind(wx.EVT_MENU, self.on_clear_recording, clearItem)
		menu_file.AppendSeparator()
		saveItem = menu_file.Append(wx.ID_ANY, "&Save recording\tCtrl-S")
		self.Bind(wx.EVT_MENU, self.on_save_recording, saveItem)
		
		item = menu_file.Append(wx.ID_ABOUT, 'About Listen', kind=wx.ITEM_NORMAL)
		self.Bind(wx.EVT_MENU, self.about, item)
		
		self.menubar.Append(menu_file, "&File")
		
		self.SetMenuBar(self.menubar)

	#Interaction with the thread
	def OnStop(self, event):
		if self.worker:
			self.worker.abort()

	def OnResult(self, event):
		self.lastDatum = event.data

	#Interface elements
	def create_main_panel(self):
		self.panel = wx.Panel(self)

		self.init_plot()
		self.canvas = FigCanvas(self.panel, wx.ID_ANY, self.fig)

		self.pause_button = wx.Button(self.panel, wx.ID_ANY, "Start")
		self.Bind(wx.EVT_BUTTON, self.on_pause_button, self.pause_button)
		
		self.save_button = wx.Button(self.panel, wx.ID_ANY, "Save")
		self.Bind(wx.EVT_BUTTON, self.on_save_recording, self.save_button)
		self.save_button.Disable()

		volume = self.getInputVolume()
		inputVolume = volume if volume != None else 50
		
		self.volumeLabel = wx.StaticText(self.panel, wx.ID_ANY, "", style=wx.ALIGN_CENTRE_HORIZONTAL)
		self.updateSliderLabel(volume)
		
		self.slider = wx.Slider(self.panel, wx.ID_ANY, inputVolume, 0, 100, wx.DefaultPosition, (150, -1), wx.SL_AUTOTICKS | wx.SL_HORIZONTAL)
		if volume == None:
			self.slider.Disable()
		else:
			#wx.EVT_SCROLL_THUMBTRACK responds to each movement, whereas wx.EVT_SCROLL_THUMBRELEASE is only after release
			self.Bind(wx.EVT_SCROLL_THUMBTRACK, self.onInputSliderChange, self.slider)
		
		self.hbox1 = wx.BoxSizer(wx.HORIZONTAL)
		self.hbox1.Add(self.pause_button, border=5, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL | wx.EXPAND)
		self.hbox1.Add(self.save_button, border=5, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL | wx.EXPAND)
		self.hbox1.Add(self.volumeLabel, border=5, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL | wx.EXPAND)
		self.hbox1.Add(self.slider, border=5, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL)

		self.vbox = wx.BoxSizer(wx.VERTICAL)
		self.vbox.Add(self.canvas, 1, flag=wx.LEFT | wx.TOP | wx.EXPAND)
		self.vbox.Add(self.hbox1, 0, flag=wx.ALIGN_LEFT | wx.TOP | wx.EXPAND)
		
		self.panel.SetSizer(self.vbox)
		self.vbox.Fit(self)

	#Graph drawing
	def init_plot(self):
		self.dpi = 100
		self.fig = Figure((3.0, 3.0), dpi=self.dpi)
		
		self.axes = self.fig.add_subplot(111)
		self.axes.set_axis_bgcolor('black')
		self.axes.set_title('Recording '+self.timeFormat(0), size=12)
		
		pylab.setp(self.axes.get_xticklabels(), visible=False)
		pylab.setp(self.axes.get_yticklabels(), visible=False)
		
		self.plot_data = self.axes.plot(self.data, linewidth=1, color=(1, 1, 0))[0]

	def on_redraw_timer(self, event):
		if not self.paused and not self.lastDatum == None:
			self.data.append(self.lastDatum)
		self.draw_plot()

	def timeFormat(self, number):
		x = int(number)
		sec = str(x % 60)
		return str(x / 60)+':'+sec.zfill(2)

	def draw_plot(self):
		gap = 100
		
		xmax = len(self.data) if len(self.data) > gap else gap
		xmin = xmax - gap
		self.axes.set_xbound(lower=xmin, upper=xmax)

		ymin = 0
		ymax = 100
		self.axes.set_ybound(lower=ymin, upper=ymax)
		
		if not self.paused:
			if self.timeStarted == None:
				self.timeStarted = time.time()
			else:
				current = 0 if self.timeStarted is None else time.time() - self.timeStarted
				self.axes.set_title('Recording '+self.timeFormat(current + self.existingDuration))
		
		self.axes.grid(True, color='gray')
		
		self.plot_data.set_xdata(np.arange(len(self.data)))
		self.plot_data.set_ydata(np.array(self.data))
		
		self.canvas.draw()

	#Input volume
	def getInputVolume(self):
		fout = os.popen('osascript -e \'get input volume of (get volume settings)\'')
		y = fout.read()
		if y:
			if y[-1] == "\n":
				y = y[:-1]
			try:
				y = int(y)
			except:
				return
			return y
	
	def setInputVolume(self):
		if self.newVolume == None:
			return
		vol = self.newVolume
		os.system('osascript -e \'tell application "System Events" to set volume input volume '+str(vol)+'\'')
		
		if self.newVolume == vol:
			self.newVolume = None
	
	def updateSliderLabel(self, value):
		value = "Disabled" if value is None else "%.2f" % round(float(value) / 100,2)
		
		self.volumeLabel.SetLabel("Input Volume: "+value)
	
	def onInputSliderChange(self, event):
		value = self.slider.GetValue()
		
		if self.newVolume == None:
			wx.CallLater(500, self.setInputVolume)
		self.newVolume = value
		
		self.updateSliderLabel(value)

	#Pause resume
	def on_pause_button(self, event):
		self.paused = not self.paused
		if self.paused:
			self.worker.pause()
			
			if self.timeStarted != None:
				self.existingDuration += time.time() - self.timeStarted
				
				self.timeStarted = None
		else:
			if self.worker is None:
				self.worker = WorkerThread(self)
			else:
				self.worker.resume()
		
		self.pause_button.SetLabel("Resume" if self.paused else "Pause")
		
		self.save_button.Enable()

	#Save
	def on_clear_recording(self, event):
		if not self.data:
			return
		
		if not self.paused:
			self.on_pause_button(None)
		
		if event != None:
			dlg = wx.MessageDialog(self, "", "Are you sure you want to clear the recording?", wx.YES_NO | wx.ICON_QUESTION)
			result = dlg.ShowModal() == wx.ID_YES
			dlg.Destroy()
			if not result:
				return
		
		self.timeStarted = None
		self.existingDuration = 0
		self.axes.set_title('Recording '+self.timeFormat(0))
		
		del self.data[:]
		
		self.pause_button.SetLabel("Start")
		self.save_button.Disable()

	def on_save_recording(self, event):
		if not self.data:
			return
		
		if not self.paused:
			self.on_pause_button(None)
		
		saveToiTunes = False
		if saveToiTunes:
			path = None
		else:
			dlg = wx.FileDialog(self, message="Save recording as...", defaultFile="recording.m4a", wildcard="M4A (*.m4a)|*.m4a", style=wx.SAVE)
			
			if dlg.ShowModal() != wx.ID_OK:
				return
			path = dlg.GetPath()
		
		if self.worker.export(path):
			self.on_clear_recording(None)
			
			return True
	
	#Quit
	def on_exit(self, event):
		if not self.paused:
			self.on_pause_button(None)
		if self.data:
			dlg = wx.MessageDialog(self, "Unsaved changes will be lost if you don't.", "Would you like to save?", wx.YES_NO | wx.ICON_QUESTION)
			result = dlg.ShowModal() == wx.ID_YES
			dlg.Destroy()
			if result:
				if not self.on_save_recording(None):
					return
		self.OnStop(event)
		
		self.Destroy()

if __name__ == '__main__':
	app = wx.App(False)
	app.frame = ListenFrame()
	app.frame.Show()
	app.MainLoop()
