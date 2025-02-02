import os
import pdfplumber
import nltk
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from .forms import PDFFileForm, KeywordForm
from .models import PDFFile, GradingCriteria
from transformers import pipeline
from django.http import HttpResponse
import joblib


# Ensure required NLTK data is downloaded
nltk.download('stopwords')
nltk.download('punkt')
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import string


# def phishing_check(request, pdf_id):
#     pdf_file = get_object_or_404(PDFFile, id=pdf_id)
#     file_path = os.path.join(settings.MEDIA_ROOT, pdf_file.file.name)
#     extracted_text = extract_text_from_pdf(file_path)

#     # Load your pre-trained phishing checking model
#     model = joblib.load('path/to/your/model.pkl')
    
#     # Predict using the model
#     ai_written_probability = model.predict_proba([extracted_text])[0][1]  # Assuming model gives probability
#     ai_percentage = ai_written_probability * 100
    
#     return render(request, 'phishing_check.html', {'ai_percentage': ai_percentage})





def clean_text(text):
    stop_words = set(stopwords.words('english'))
    words = word_tokenize(text)
    cleaned_words = [word for word in words if word.lower() not in stop_words and word not in string.punctuation]
    return ' '.join(cleaned_words)

def extract_text_from_pdf(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    
    cleaned_text = clean_text(text)
    word_count = len(cleaned_text.split())
    return cleaned_text

def upload_pdf(request):
    if request.method == 'POST':
        form = PDFFileForm(request.POST, request.FILES)
        if form.is_valid():
            pdf_file = form.save()
            return redirect('show_extracted_text', pdf_id=pdf_file.id)
    else:
        form = PDFFileForm()
    return render(request, 'upload.html', {'form': form})

def show_extracted_text(request, pdf_id):
    pdf_file = get_object_or_404(PDFFile, id=pdf_id)
    file_path = os.path.join(settings.MEDIA_ROOT, pdf_file.file.name)
    extracted_text = extract_text_from_pdf(file_path)
    num_words = len(extracted_text.split())  # Counting the number of words

    # Create GradingCriteria if it doesn't exist
    grading_criteria, created = GradingCriteria.objects.get_or_create(pdf=pdf_file)
    
    return render(request, 'show_extracted_text.html', {'text': extracted_text, 'pdf_id': pdf_id, 'num_words': num_words})

def keyword_form(request, pdf_id):
    pdf_file = get_object_or_404(PDFFile, id=pdf_id)
    grading_criteria, created = GradingCriteria.objects.get_or_create(pdf=pdf_file)
    
    if request.method == 'POST':
        form = KeywordForm(request.POST, instance=grading_criteria)
        if form.is_valid():
            form.save()
            return redirect('grade_pdf', pdf_id=pdf_id)
    else:
        form = KeywordForm(instance=grading_criteria)
    return render(request, 'keyword_form.html', {'form': form, 'pdf_id': pdf_id})

# def generate_feedback(grade, score):
#     feedback = []

#     if grade not in ['A', 'S']:
#         if score < 50:
#             feedback.append("Your score is quite low. Try to focus on providing more relevant content.")
#         else:
#             feedback.append("Consider adding more detailed explanations to support your points.")
#             feedback.append("Try to use a wider range of vocabulary to express your ideas.")
#             feedback.append("Make sure to address all aspects of the question or topic.")
#             feedback.append("Check for any grammatical errors or spelling mistakes.")

#     return feedback


def grade_pdf(request, pdf_id):
    pdf_file = get_object_or_404(PDFFile, id=pdf_id)
    grading_criteria = pdf_file.criteria
    file_path = os.path.join(settings.MEDIA_ROOT, pdf_file.file.name)
    extracted_text = extract_text_from_pdf(file_path)
    
    # Calculate grade and score based on grading criteria
    grade, score = calculate_grade_and_score(extracted_text, grading_criteria)
    # feedback = generate_feedback(grade, score)
    
    return render(request, 'result.html', {'text': extracted_text, 'grade': grade, 'score': score})

def calculate_grade_and_score(text, grading_criteria):
    # Load pre-trained BERT model for question answering
    model = pipeline('question-answering', model="distilbert-base-uncased-distilled-squad")
    
    keywords = grading_criteria.keywords.split(',')
    min_words = grading_criteria.min_words
    max_words = grading_criteria.max_words
    
    # Count the occurrence of keywords in the text
    keyword_count = sum(text.lower().count(keyword.lower()) for keyword in keywords)
    
    # Calculate the length score based on the ratio of actual words to the specified word range
    words = text.split()
    total_words = len(words)
    
    # Check if the total words are within the specified range
    if total_words < min_words:
        length_score = 0  # Penalty for too few words
    elif total_words > max_words:
        length_score = 50  # Adjust score for too many words
    else:
        length_score = (total_words / max_words) * 100
    
    # Use the model to assess the quality of the answer
    qa_input = {
        'question': 'How relevant is this text to the given keywords?',
        'context': text
    }
    model_output = model(qa_input)
    relevance_score = model_output['score'] * 100
    
    # Normalize scores and combine them
    keyword_score = (keyword_count / len(keywords)) * 100 if keywords else 0
    length_score = min(length_score, 100)
    relevance_score = min(relevance_score, 100)
    
    # Combine the scores based on your weighting criteria
    score = (keyword_score + length_score + relevance_score) / 3
    
    # Ensure score is within 0 to 100 range
    score = min(max(score, 0), 100)
    
    # Determine grade based on score
    if score >= 90:
        grade = 'A'
    elif score >= 75:
        grade = 'B'
    elif score >= 50:
        grade = 'C'
    elif score >= 33:
        grade = 'D'
    else:
        grade = 'F'
    
    if total_words == 0:
        grade = 'N'  # Not attended
    
    return grade, score



