import logging
import numpy as np
from django.shortcuts import render, redirect
from .forms import MarkEntryForm
from .models import Year, Board, SubjectStat
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from scipy.stats import norm
import pandas as pd

logger = logging.getLogger(__name__)

# Map view subject names to database subject names
SUBJECT_NAME_MAPPING = {
    'maths': 'mathematics',
    'physics': 'physics',
    'chemistry': 'chemistry'
}

def intro(request):
    """Show introduction page with year selection"""
    years = Year.objects.all().order_by('-value')
    return render(request, 'keam_app/intro.html', {'years': years})

def select_year(request):
    """Handle year selection form submission"""
    if request.method == 'POST':
        year_id = request.POST.get('year')
        if year_id:
            request.session['year_id'] = year_id
            return redirect('keam_app:marks_form')
    return redirect('keam_app:intro')

# Helper function to get database subject name
def get_db_subject_name(view_subject):
    return SUBJECT_NAME_MAPPING.get(view_subject.lower(), view_subject)

# Enhanced Normalization Function with error handling
def normalize_mark(x, mean_board, sd_board, mean_kerala, sd_kerala):
    try:
        # Handle division by zero and invalid SD values
        if sd_board <= 0:
            sd_board = 0.1  # Prevent division by zero
        if sd_kerala <= 0:
            sd_kerala = 0.1

        z_score = (x - mean_board) / sd_board

        # Handle extreme z-scores to avoid infinite values
        if z_score < -8:
            percentile = 0.0001
        elif z_score > 8:
            percentile = 0.9999
        else:
            percentile = norm.cdf(z_score)

        # Clamp percentiles to avoid infinite z-scores
        clamped_percentile = max(0.0001, min(percentile, 0.9999))
        z_kerala = norm.ppf(clamped_percentile)
        normalized = z_kerala * sd_kerala + mean_kerala

        return {
            "student_mark": x,
            "mean_source": mean_board,
            "sd_source": sd_board,
            "z_score": z_score,
            "percentile": percentile,
            "z_kerala": z_kerala,
            "mean_kerala": mean_kerala,
            "sd_kerala": sd_kerala,
            "normalized_mark": normalized
        }
    except Exception as e:
        logger.error(f"Normalization error: {e}")
        # Fallback to linear scaling
        return {
            "normalized_mark": (x / 100) * mean_kerala,
            "error": str(e)
        }

# Single Student Normalization with proper weight calculation
# views.py
def result(request):
    if request.method != 'POST':
        return redirect('keam_app:marks_form')

    # Get year from session
    year_id = request.session.get('year_id')
    if not year_id:
        return redirect('keam_app:intro')

    try:
        year = Year.objects.get(id=year_id)
    except Year.DoesNotExist:
        return redirect('keam_app:intro')

    # Pass year to form
    form = MarkEntryForm(request.POST, year=year)
    error_msgs = []
    context = {'result': None, 'errors': error_msgs}

    if not form.is_valid():
        # Add form errors to context
        error_msgs.extend(form.errors.values())
        return render(request, 'keam_app/results.html', context)

    # Rest of your calculation code...
    try:
        board = form.cleaned_data['board']
        entrance = form.cleaned_data.get('entrance', 0)
        marks = {
            'maths': form.cleaned_data['maths'],
            'physics': form.cleaned_data['physics'],
            'chemistry': form.cleaned_data['chemistry']
        }

        # Get or create Kerala board
        kerala_board, created = Board.objects.get_or_create(
            name="Kerala HSE",
            year=board.year,
            defaults={'name': "Kerala HSE", 'year': board.year}
        )
        if created:
            logger.warning(f"Created new Kerala HSE board for year {board.year}")

        # Get Kerala stats with fallbacks
        kerala_stats = {}
        for view_subject, mark in marks.items():
            db_subject = get_db_subject_name(view_subject)
            stat = SubjectStat.objects.filter(
                board=kerala_board,
                subject__iexact=db_subject
            ).first()
            kerala_stats[view_subject] = (stat.mean, stat.sd) if stat else (70.0, 10.0)
            if not stat:
                error_msgs.append(f"No Kerala HSE stats for {view_subject} - using default values")

        # Normalize marks
        normalized = {}
        weights = {'maths': 5, 'physics': 3, 'chemistry': 2}
        weighted_total = 0
        total_weights = sum(weights.values())

        for view_subject, mark in marks.items():
            db_subject = get_db_subject_name(view_subject)
            # Get board-specific stats
            stat = SubjectStat.objects.filter(
                board=board,
                subject__iexact=db_subject
            ).first()

            if not stat:
                error_msgs.append(f"No {board.name} stats for {view_subject} - using fallback values")
                stat_mean, stat_sd = 70.0, 10.0
            else:
                stat_mean, stat_sd = stat.mean, stat.sd

            mean_kerala, sd_kerala = kerala_stats[view_subject]
            norm_data = normalize_mark(mark, stat_mean, stat_sd, mean_kerala, sd_kerala)

            if 'error' in norm_data:
                error_msgs.append(f"Normalization failed for {view_subject}: {norm_data['error']}")
                # Use fallback normalization
                norm_data['normalized_mark'] = (mark / 100) * mean_kerala

            norm_data["board_name"] = board.name
            normalized[view_subject] = norm_data
            weighted_total += norm_data["normalized_mark"] * weights[view_subject]

        normalized_total = round(weighted_total / total_weights, 4)
        final_score = round((normalized_total + entrance) / 2, 4) if entrance else normalized_total

        context['result'] = {
            'normalized': normalized,
            'normalized_total': normalized_total,
            'final_score': final_score,
            'original': {**marks, 'entrance': entrance}
        }

    except Exception as e:
        logger.exception("Error in result calculation")
        error_msgs.append("An error occurred during calculation. Please try again.")

    return render(request, 'keam_app/results.html', context)

# Batch Normalization with proper error handling
@csrf_exempt
def upload_and_process(request):
    if request.method == "POST" and request.FILES.get('marks_file'):
        try:
            file = request.FILES['marks_file']
            if file.name.endswith('.xlsx'):
                df = pd.read_excel(file, engine='openpyxl')
            else:
                df = pd.read_csv(file)
        except Exception as e:
            logger.error(f"File upload error: {e}")
            return render(request, 'keam_app/results.html', {
                'errors': ["Unable to process uploaded file. Please check the format."]
            })

        df.columns = df.columns.str.strip()
        year_id = request.session.get('year_id')
        if not year_id:
            return redirect('keam_app:intro')

        try:
            year = Year.objects.get(id=year_id)
        except Year.DoesNotExist:
            return redirect('keam_app:intro')

        # Get/create Kerala board and stats
        kerala_board, created = Board.objects.get_or_create(
            name="Kerala HSE",
            year=year,
            defaults={'name': "Kerala HSE", 'year': year}
        )
        if created:
            logger.warning(f"Created new Kerala HSE board for year {year}")

        kerala_stats = {}
        for view_subject in ['maths', 'physics', 'chemistry']:
            db_subject = get_db_subject_name(view_subject)
            stat = SubjectStat.objects.filter(
                board=kerala_board,
                subject__iexact=db_subject
            ).first()
            kerala_stats[view_subject] = (stat.mean, stat.sd) if stat else (70.0, 10.0)

        weights = {'maths': 5, 'physics': 3, 'chemistry': 2}
        total_weights = sum(weights.values())
        results = []
        errors = []

        for index, row in df.iterrows():
            try:
                board_name = str(row.get('Board', '')).strip()
                if not board_name:
                    errors.append(f"Row {index + 2}: Missing board name")
                    continue

                try:
                    entrance = float(row.get('Entrance', 0))
                except (ValueError, TypeError):
                    entrance = 0

                # Handle different capitalization
                marks = {}
                for view_subject in ['maths', 'physics', 'chemistry']:
                    col_name = view_subject.capitalize()
                    mark_value = row.get(col_name) or row.get(view_subject) or row.get(view_subject.upper()) or 0
                    try:
                        marks[view_subject] = float(mark_value)
                    except (ValueError, TypeError):
                        marks[view_subject] = 0

                board_obj, _ = Board.objects.get_or_create(
                    name=board_name,
                    year=year,
                    defaults={'name': board_name, 'year': year}
                )

                weighted_total = 0
                subject_results = {}
                row_errors = []

                for view_subject, mark in marks.items():
                    db_subject = get_db_subject_name(view_subject)
                    stat = SubjectStat.objects.filter(
                        board=board_obj,
                        subject__iexact=db_subject
                    ).first()

                    if not stat:
                        row_errors.append(f"No stats for {view_subject}")
                        stat_mean, stat_sd = 70.0, 10.0
                    else:
                        stat_mean, stat_sd = stat.mean, stat.sd

                    mean_kerala, sd_kerala = kerala_stats[view_subject]
                    norm_data = normalize_mark(mark, stat_mean, stat_sd, mean_kerala, sd_kerala)

                    if 'error' in norm_data:
                        row_errors.append(f"Normalization failed for {view_subject}")

                    subject_results[view_subject] = norm_data
                    weighted_total += norm_data["normalized_mark"] * weights[view_subject]

                normalized_total = round(weighted_total / total_weights, 4)
                final_score = round((normalized_total + entrance) / 2, 4) if entrance else normalized_total

                results.append({
                    'board': board_name,
                    'marks': marks,
                    'entrance': entrance,
                    'normalized_total': normalized_total,
                    'final_score': final_score,
                    'subject_results': subject_results,
                    'errors': row_errors
                })

                if row_errors:
                    errors.append(f"Row {index + 2}: " + ", ".join(row_errors))

            except Exception as e:
                errors.append(f"Row {index + 2}: Error processing - {str(e)}")
                continue

        return render(request, 'keam_app/bulk_results.html', {
            'results': results,
            'errors': errors
        })

    return redirect('keam_app:marks_form')


def marks_form(request):
    """Display the marks entry form"""
    year_id = request.session.get('year_id')
    if not year_id:
        return redirect('keam_app:intro')

    try:
        year = Year.objects.get(id=year_id)
    except Year.DoesNotExist:
        return redirect('keam_app:intro')

    if request.method == 'POST':
        form = MarkEntryForm(request.POST, year=year)  # Pass year to form
        if form.is_valid():
            return redirect('keam_app:result')
    else:
        form = MarkEntryForm(year=year)  # Pass year to form

    return render(request, 'keam_app/form.html', {
        'form': form,
        'year': year
    })

# Webhook Endpoint
@csrf_exempt
def webhook_listener(request):
    if request.method == 'POST':
        try:
            return JsonResponse({'status': 'success', 'message': 'Webhook processed'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid method'}, status=400)