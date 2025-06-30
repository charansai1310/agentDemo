import os
import torch
import pandas as pd
from torch.utils.data import Dataset, DataLoader
from transformers import DistilBertTokenizer, DistilBertForSequenceClassification
from torch.optim import AdamW
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score
from torch.nn.functional import softmax
import pickle

# Fix environment issues
os.environ["TOKENIZERS_PARALLELISM"] = "false"
from transformers import logging
logging.set_verbosity_error()

# Constants
MODEL_NAME = "distilbert-base-uncased"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_SAVE_PATH = os.path.join(SCRIPT_DIR, "intent_classifier_model.pt")
LABEL_ENCODER_PATH = os.path.join(SCRIPT_DIR, "label_encoder.pkl")

class IntentDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_length=64):
        self.encodings = tokenizer(texts, truncation=True, padding=True, max_length=max_length)
        self.labels = labels

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {key: torch.tensor(val[idx]) for key, val in self.encodings.items()}
        item['labels'] = torch.tensor(self.labels[idx])
        return item

class IntentClassifier:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = DistilBertTokenizer.from_pretrained(MODEL_NAME)
        self.model = DistilBertForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=7).to(self.device)
        self.label_encoder = LabelEncoder()
        self.is_loaded = False 

    def train(self, csv_path, batch_size=16, epochs=5, lr=5e-5):
        df = pd.read_csv(csv_path)
        texts = df['text'].tolist()
        labels = self.label_encoder.fit_transform(df['intent'].tolist())

        dataset = IntentDataset(texts, labels, self.tokenizer)
        dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True, pin_memory=False)

        optimizer = AdamW(self.model.parameters(), lr=lr)
        self.model.train()

        for epoch in range(epochs):
            total_loss = 0
            for batch in dataloader:
                batch = {k: v.to(self.device) for k, v in batch.items()}
                outputs = self.model(**batch)
                loss = outputs.loss
                loss.backward()
                optimizer.step()
                optimizer.zero_grad()
                total_loss += loss.item()
            print(f"Epoch {epoch+1}/{epochs}, Loss: {total_loss:.4f}")

        torch.save(self.model.state_dict(), MODEL_SAVE_PATH)
        with open(LABEL_ENCODER_PATH, "wb") as f:
            pickle.dump(self.label_encoder, f)
        self.is_loaded = True  # Mark as loaded after training

    def load_model(self):
        self.model.load_state_dict(torch.load(MODEL_SAVE_PATH, map_location=self.device))
        self.model.eval()
        with open(LABEL_ENCODER_PATH, "rb") as f:
            self.label_encoder = pickle.load(f)
        self.is_loaded = True  # Mark as loaded

    def predict(self, text):
        # Load model if not already loaded
        if not self.is_loaded:
            self.load_model()

        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, padding=True, max_length=64).to(self.device)
        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = softmax(outputs.logits, dim=1)
            conf, pred = torch.max(probs, dim=1)

        label = self.label_encoder.inverse_transform(pred.cpu().numpy())[0]
        confidence = conf.item()
        return {"label": label, "confidence": round(confidence, 4)}

if __name__ == "__main__":
    classifier = IntentClassifier()
    csv_path = "datasets/intent_dataset.csv"
    classifier.train(csv_path)
    # classifier.load_model()
    # test_text = "How to reduce fat without loosing weight?"
    # result = classifier.predict(test_text)
    # print("Prediction Result:", result)