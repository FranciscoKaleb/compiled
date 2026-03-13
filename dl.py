# from transformers import AutoModelForSequenceClassification, AutoTokenizer

# model_name = "distilbert-base-uncased-finetuned-sst-2-english"

# model = AutoModelForSequenceClassification.from_pretrained(model_name)
# tokenizer = AutoTokenizer.from_pretrained(model_name)

# # Save locally
# model.save_pretrained("./my_model")
# tokenizer.save_pretrained("./my_model")
















# from transformers import AutoTokenizer, AutoModelForSequenceClassification

# model_name = "cardiffnlp/twitter-xlm-roberta-base-sentiment"

# tokenizer = AutoTokenizer.from_pretrained(model_name)
# model = AutoModelForSequenceClassification.from_pretrained(model_name)

# tokenizer.save_pretrained("./bert1_sentiment_model")
# model.save_pretrained("./bert1_sentiment_model")



















# from transformers import AutoModelForImageClassification, AutoImageProcessor

# model_name = "google/vit-base-patch16-224"

# processor = AutoImageProcessor.from_pretrained(model_name)
# model = AutoModelForImageClassification.from_pretrained(model_name)

# processor.save_pretrained("./vit_model")
# model.save_pretrained("./vit_model")

# print("Model downloaded and saved locally.")



















#  next we will download this google/vit-large-patch16-224
# from transformers import AutoModelForImageClassification, AutoImageProcessor

# def download_vit_large_model():
#     """Download and save Google's ViT large model locally."""
#     model_name = "google/vit-large-patch16-224"
    
#     processor = AutoImageProcessor.from_pretrained(model_name)
#     model = AutoModelForImageClassification.from_pretrained(model_name)
    
#     processor.save_pretrained("./vit_large_model")
#     model.save_pretrained("./vit_large_model")
    
#     print("ViT large model downloaded and saved locally.")

# download_vit_large_model()










# next to download is IDEA-Research/grounding-dino-base model
# from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

# model_name = "IDEA-Research/grounding-dino-base"

# processor = AutoProcessor.from_pretrained(model_name)
# model = AutoModelForZeroShotObjectDetection.from_pretrained(model_name)

# processor.save_pretrained("./grounding_dino")
# model.save_pretrained("./grounding_dino")

# print("Model downloaded successfully.")














# next is microsoft/trocr-large-printed
# below is the complete code to download and save the model locally
# from transformers import TrOCRProcessor, VisionEncoderDecoderModel

# model_name = "microsoft/trocr-large-printed"

# # Download processor
# processor = TrOCRProcessor.from_pretrained(model_name)

# # Download model
# model = VisionEncoderDecoderModel.from_pretrained(model_name)

# # Save locally
# processor.save_pretrained("./trocr_large_model")
# model.save_pretrained("./trocr_large_model")

# print("Model downloaded and saved locally.")























# from transformers import NougatProcessor, VisionEncoderDecoderModel
# from PIL import Image

# model_name = "facebook/nougat-base"

# # download
# processor = NougatProcessor.from_pretrained(model_name)
# model = VisionEncoderDecoderModel.from_pretrained(model_name)

# # save locally
# processor.save_pretrained("./nougat_base")
# model.save_pretrained("./nougat_base")









# # DeepSeek‑OCR
# from huggingface_hub import snapshot_download

# # Model name on Hugging Face
# model_name = "deepseek-ai/DeepSeek-OCR"

# # Download the entire repo snapshot
# snapshot_download(repo_id=model_name, local_dir="./deepseek_ocr")

# print("DeepSeek-OCR model downloaded locally.")














# from transformers import LightOnOcrProcessor, LightOnOcrForConditionalGeneration

# model_name = "lightonai/LightOnOCR-2-1B"

# # Download model weights + processor
# processor = LightOnOcrProcessor.from_pretrained(model_name)
# model = LightOnOcrForConditionalGeneration.from_pretrained(model_name)

# # Save locally
# processor.save_pretrained("./LightOnOCR_2_1B")
# model.save_pretrained("./LightOnOCR_2_1B")

# print("LightOnOCR‑2‑1B model downloaded and saved locally.")















# from huggingface_hub import snapshot_download

# # Default PaddleOCR‑VL model
# model_name = "PaddlePaddle/PaddleOCR-VL"

# snapshot_download(repo_id=model_name, local_dir="./PaddleOCR_VL")

# print("PaddleOCR‑VL model saved locally.")


















# from transformers import AutoImageProcessor, SiglipForImageClassification

# model_name = "prithivMLmods/Human-vs-NonHuman-Detection"

# # Download
# processor = AutoImageProcessor.from_pretrained(model_name)
# model = SiglipForImageClassification.from_pretrained(model_name)

# # Save locally
# local_path = "./Human_NonHuman_Model"

# processor.save_pretrained(local_path)
# model.save_pretrained(local_path)

# print("Model downloaded and saved locally.")






















# from transformers import DetrImageProcessor, DetrForObjectDetection

# model_name = "facebook/detr-resnet-50"

# # Download processor + model
# processor = DetrImageProcessor.from_pretrained(model_name)
# model = DetrForObjectDetection.from_pretrained(model_name)

# # Save locally
# processor.save_pretrained("./detr-resnet-50")
# model.save_pretrained("./detr-resnet-50")

# print("Model saved to ./detr-resnet-50")

















# from insightface.app import FaceAnalysis

# app = FaceAnalysis(
#     providers=['CPUExecutionProvider'],
#     root="./insightface_models"
# )

# app.prepare(ctx_id=-1)

# print("Downloaded to ./insightface_models")










from insightface.app import FaceAnalysis

# Initialize the app with the model name "buffalo_l"
app = FaceAnalysis(
    name="buffalo_l",             # the model you want
    providers=["CPUExecutionProvider"],  # CPU only
    root="./insightface_models"   # where to save the model
)

# This will automatically download the model if not present
app.prepare(ctx_id=-1)

print("buffalo_l model downloaded to ./insightface_models")