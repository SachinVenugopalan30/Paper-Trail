"""
Evaluation metrics for PDF text extraction quality assessment.

This module provides functions to calculate:
- Character Error Rate (CER): measures character-level accuracy
- Word Error Rate (WER): measures word-level accuracy  
- Text similarity: measures overall text similarity using sequence matching
"""

import difflib
from typing import Optional

try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False


def _normalize_text(text: str) -> str:
    """
    Normalize text for fair comparison.
    
    Args:
        text: Raw text string
        
    Returns:
        Normalized text with consistent whitespace
    """
    if not text:
        return ""
    # Normalize whitespace: collapse multiple spaces/newlines to single space
    return " ".join(text.split())


def calculate_cer(predicted: str, ground_truth: str) -> float:
    """
    Calculate Character Error Rate (CER) between predicted and ground truth text.
    
    CER = (Substitutions + Insertions + Deletions) / Total Characters in Ground Truth
    
    Args:
        predicted: The predicted/extracted text
        ground_truth: The reference/ground truth text
        
    Returns:
        Character Error Rate as a float between 0.0 and 1.0
        Returns 1.0 if ground_truth is empty and predicted is not
        Returns 0.0 if both are empty
        
    Example:
        >>> calculate_cer("hello", "hallo")
        0.2
        >>> calculate_cer("test", "test")
        0.0
    """
    predicted = _normalize_text(predicted)
    ground_truth = _normalize_text(ground_truth)
    
    # Edge cases
    if not ground_truth and not predicted:
        return 0.0
    if not ground_truth:
        return 1.0
    if not predicted:
        return 1.0
    
    # Use difflib.SequenceMatcher to find differences
    matcher = difflib.SequenceMatcher(None, predicted, ground_truth)
    
    # Calculate edit distance using the opcodes
    edit_distance = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace':
            # Replace: count as max of deletion and insertion
            edit_distance += max(i2 - i1, j2 - j1)
        elif tag == 'delete':
            # Deletion from predicted
            edit_distance += i2 - i1
        elif tag == 'insert':
            # Insertion into predicted
            edit_distance += j2 - j1
        # 'equal' tag means no changes needed
    
    return edit_distance / len(ground_truth)


def calculate_wer(predicted: str, ground_truth: str) -> float:
    """
    Calculate Word Error Rate (WER) between predicted and ground truth text.
    
    WER = (Substitutions + Insertions + Deletions) / Total Words in Ground Truth
    
    Args:
        predicted: The predicted/extracted text
        ground_truth: The reference/ground truth text
        
    Returns:
        Word Error Rate as a float between 0.0 and 1.0
        Returns 1.0 if ground_truth is empty and predicted is not
        Returns 0.0 if both are empty
        
    Example:
        >>> calculate_wer("the quick brown fox", "the fast brown fox")
        0.25
        >>> calculate_wer("hello world", "hello world")
        0.0
    """
    predicted = _normalize_text(predicted)
    ground_truth = _normalize_text(ground_truth)
    
    # Split into words
    pred_words = predicted.split() if predicted else []
    gt_words = ground_truth.split() if ground_truth else []
    
    # Edge cases
    if not gt_words and not pred_words:
        return 0.0
    if not gt_words:
        return 1.0
    if not pred_words:
        return 1.0
    
    # Use difflib.SequenceMatcher on word lists
    matcher = difflib.SequenceMatcher(None, pred_words, gt_words)
    
    # Calculate word-level edit distance
    edit_distance = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'replace':
            edit_distance += max(i2 - i1, j2 - j1)
        elif tag == 'delete':
            edit_distance += i2 - i1
        elif tag == 'insert':
            edit_distance += j2 - j1
    
    return edit_distance / len(gt_words)


def text_similarity(text1: str, text2: str, method: str = "auto") -> float:
    """
    Calculate text similarity between two strings.
    
    Returns a similarity score between 0.0 (completely different) and 1.0 (identical).
    
    Args:
        text1: First text string
        text2: Second text string
        method: Similarity method to use:
            - "auto": Use rapidfuzz if available, else difflib
            - "difflib": Use Python's difflib.SequenceMatcher
            - "rapidfuzz": Use rapidfuzz library (faster, more accurate)
            
    Returns:
        Similarity ratio as a float between 0.0 and 1.0
        
    Example:
        >>> text_similarity("hello world", "hello world")
        1.0
        >>> text_similarity("hello", "hallo")
        0.8
    """
    text1 = _normalize_text(text1)
    text2 = _normalize_text(text2)
    
    # Edge cases
    if not text1 and not text2:
        return 1.0
    if not text1 or not text2:
        return 0.0
    
    # Determine which method to use
    use_rapidfuzz = RAPIDFUZZ_AVAILABLE and (method == "rapidfuzz" or method == "auto")
    
    if use_rapidfuzz:
        # Use rapidfuzz for faster, more accurate matching
        # ratio() returns 0-100, convert to 0-1
        from rapidfuzz import fuzz
        return fuzz.ratio(text1, text2) / 100.0
    else:
        # Use difflib as fallback
        matcher = difflib.SequenceMatcher(None, text1, text2)
        return matcher.ratio()


def calculate_all_metrics(predicted: str, ground_truth: str) -> dict:
    """
    Calculate all available metrics at once.
    
    Args:
        predicted: The predicted/extracted text
        ground_truth: The reference/ground truth text
        
    Returns:
        Dictionary containing all metrics:
        - cer: Character Error Rate
        - wer: Word Error Rate
        - similarity: Text similarity score
        - pred_length: Length of predicted text
        - gt_length: Length of ground truth text
        - pred_words: Word count of predicted text
        - gt_words: Word count of ground truth text
    """
    return {
        "cer": calculate_cer(predicted, ground_truth),
        "wer": calculate_wer(predicted, ground_truth),
        "similarity": text_similarity(predicted, ground_truth),
        "pred_length": len(_normalize_text(predicted)),
        "gt_length": len(_normalize_text(ground_truth)),
        "pred_words": len(_normalize_text(predicted).split()) if predicted else 0,
        "gt_words": len(_normalize_text(ground_truth).split()) if ground_truth else 0,
    }


if __name__ == "__main__":
    # Simple test cases
    test_cases = [
        ("hello world", "hello world"),
        ("hello", "hallo"),
        ("the quick brown fox", "the fast brown fox jumps"),
        ("", "something"),
        ("something", ""),
        ("", ""),
    ]
    
    print("Metrics Test Results:")
    print("=" * 80)
    for pred, gt in test_cases:
        metrics = calculate_all_metrics(pred, gt)
        print(f"Predicted: '{pred}'")
        print(f"Ground Truth: '{gt}'")
        print(f"  CER: {metrics['cer']:.3f}")
        print(f"  WER: {metrics['wer']:.3f}")
        print(f"  Similarity: {metrics['similarity']:.3f}")
        print("-" * 80)
