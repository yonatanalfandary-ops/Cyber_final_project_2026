import face_recognition
import json
import numpy as np
image = face_recognition.load_image_file("face_data\known_face.jpg")
encoding = face_recognition.face_encodings(image)[0]

s_encoding = json.dumps(encoding.tolist())

fromjson_encoding = np.array(json.loads(s_encoding))
print(encoding)
print(s_encoding)
print(fromjson_encoding)

