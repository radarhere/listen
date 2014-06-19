import wx, os, sys

class About(wx.Frame):
	def __init__(self):
		wx.Frame.__init__(self, None, wx.ID_ANY, 'About Me', style=wx.FRAME_EX_METAL)
		
		version = '0.0.1'
		aboutText = ['Listen is a recording program',
		'developed by Radartech.',
		'',
		'Version: '+version]
		
		aboutTextLabel = wx.StaticText(self, wx.ID_ANY, "\n".join(aboutText), style=wx.ALIGN_CENTRE_HORIZONTAL)
		
		localPath = sys.path[0].replace('/lib/python27.zip','')
		image = wx.Image(os.path.join(localPath, 'Listen.png'), wx.BITMAP_TYPE_ANY)
		imageBitmap = wx.StaticBitmap(self, wx.ID_ANY, wx.BitmapFromImage(image))
		
		sizer = wx.GridBagSizer(1, 1)
		sizer.Add(imageBitmap, (0, 0), (1, 1), wx.BOTTOM | wx.TOP | wx.LEFT, border = 20)
		sizer.Add(aboutTextLabel, (1, 0), (1, 1), wx.BOTTOM | wx.LEFT | wx.EXPAND, border = 20)
		self.SetSizerAndFit(sizer)
		self.Centre()
		
		self.SetBackgroundColour((255,255,255))
		self.Bind(wx.EVT_LEFT_DOWN, self.onClose)
		imageBitmap.Bind(wx.EVT_LEFT_DOWN, self.onClose)
		aboutTextLabel.Bind(wx.EVT_LEFT_DOWN, self.onClose)
		
		self.Show()

	def onClose(self, event):
		self.Destroy()