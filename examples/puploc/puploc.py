from ctypes import *

import numpy as np
import os
import cv2
import time

os.system('go build -o puploc.so -buildmode=c-shared puploc.go')
pigo = cdll.LoadLibrary('./puploc.so')

MAX_NDETS = 2024
ARRAY_DIM = 5

# define class GoPixelSlice to map to:
# C type struct { void *data; GoInt len; GoInt cap; }
class GoPixelSlice(Structure):
	_fields_ = [
		("pixels", POINTER(c_ubyte)), ("len", c_longlong), ("cap", c_longlong),
	]

# Obtain the camera pixels and transfer them to Go through Ctypes.
def process_frame(pixs):
	dets = np.zeros(ARRAY_DIM * MAX_NDETS, dtype=np.float32)
	pixels = cast((c_ubyte * len(pixs))(*pixs), POINTER(c_ubyte))

	# call FindFaces
	faces = GoPixelSlice(pixels, len(pixs), len(pixs))
	pigo.FindFaces.argtypes = [GoPixelSlice]
	pigo.FindFaces.restype = c_void_p

	# Call the exported FindFaces function from Go.
	ndets = pigo.FindFaces(faces)
	data_pointer = cast(ndets, POINTER((c_longlong * ARRAY_DIM) * MAX_NDETS))

	if data_pointer :
		buffarr = ((c_longlong * ARRAY_DIM) * MAX_NDETS).from_address(addressof(data_pointer.contents))
		res = np.ndarray(buffer=buffarr, dtype=c_longlong, shape=(ARRAY_DIM, ARRAY_DIM))

		# The first value of the buffer aray represents the buffer length.
		dets_len = res[0][0]
		res = np.delete(res, 0, 0) # delete the first element from the array

		# We have to consider the pupil pair added into the list.
		# That's why we are multiplying the detection length with 3.
		dets = list(res.reshape(-1, ARRAY_DIM))[0:dets_len*3]
		return dets

# initialize the camera
width, height = 640, 480
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

showPupil = True
showEyes = False

while(True):
	ret, frame = cap.read()
	pixs = np.ascontiguousarray(frame[:, :, 1].reshape((frame.shape[0], frame.shape[1])))
	pixs = pixs.flatten()

	# We need to make sure that the whole frame size is transfered over Go, 
	# otherwise we might getting an index out of range panic error.
	if len(pixs) == width*height:
		dets = process_frame(pixs) # pixs needs to be numpy.uint8 array

		if dets is not None:
			# We know that the detected faces are taking place in the first positions of the multidimensional array.
			for det in dets:
				if det[3] > 50:
					if det[4] == 1: # 1 == face; 0 == pupil
						cv2.circle(frame, (int(det[1]), int(det[0])), int(det[2]/2.0), (0, 0, 255), 2)
					else:
						if showPupil:
							cv2.circle(frame, (int(det[1]), int(det[0])), 4, (0, 0, 255), -1, 8, 0)
						if showEyes:
							cv2.rectangle(frame,
								(int(det[1])-int(det[2]), int(det[0])-int(det[2])),
								(int(det[1])+int(det[2]), int(det[0])+int(det[2])),
								(0, 255, 0), 2
							)

	cv2.imshow('Pupil / eyes localization', frame)

	key = cv2.waitKey(1)
	if key & 0xFF == ord('q'):
		break
	elif key & 0xFF == ord('w'):
		showPupil = not showPupil
	elif key & 0xFF == ord('e'):
		showEyes = not showEyes

cap.release()
cv2.destroyAllWindows()