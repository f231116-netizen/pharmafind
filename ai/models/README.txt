Text reading (OCR) models used by ai/ocr.py

ch_PP-OCRv3_det_infer.onnx   text detection   (where is the text?)
ch_PP-OCRv3_rec_infer.onnx   text recognition (what does it say?)
ppocr_keys.txt               the characters the recognizer can output

From PaddleOCR (PP-OCRv3), ONNX versions as shipped in the rapidocr-onnxruntime
package. License: Apache License 2.0.
We run them with OpenCV's DNN module instead of onnxruntime, because onnxruntime
has no build for Python 3.15 yet.
