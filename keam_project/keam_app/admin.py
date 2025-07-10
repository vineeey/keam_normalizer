from django.contrib import admin
from django import forms
from django.shortcuts import render, redirect
from django.urls import path
import pandas as pd
from .models import Year, Board, SubjectStat
import logging
import traceback

logger = logging.getLogger(__name__)

class YearAdmin(admin.ModelAdmin):
    list_display = ('value',)
    search_fields = ('value',)
    ordering = ('-value',)

class BoardAdmin(admin.ModelAdmin):
    list_display = ('name', 'year')
    list_filter = ('year',)
    search_fields = ('name',)
    ordering = ('year', 'name')

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['year'].queryset = Year.objects.all().order_by('-value')
        return form

class UploadStatsForm(forms.Form):
    stats_file = forms.FileField(label="Upload Excel or CSV File")

@admin.register(SubjectStat)
class SubjectStatAdmin(admin.ModelAdmin):
    change_list_template = "admin/subject_stats_change_list.html"
    list_display = ('board', 'subject', 'mean', 'sd')
    search_fields = ('board__name', 'subject')
    list_filter = ('board__year',)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'upload-stats/',
                self.admin_site.admin_view(self.upload_stats),
                name='keam_app_subjectstat_upload_stats'
            )
        ]
        return custom_urls + urls

    def upload_stats(self, request):
        if request.method == "POST":
            form = UploadStatsForm(request.POST, request.FILES)
            if form.is_valid():
                file = request.FILES['stats_file']
                try:
                    if file.name.endswith('.csv'):
                        df = pd.read_csv(
                            file,
                            encoding='utf-8-sig',
                            quotechar='"',
                            skipinitialspace=True
                        )
                    else:
                        df = pd.read_excel(file, engine='openpyxl')

                    df.columns = df.columns.str.strip().str.lower()

                    column_mapping = {
                        'year': ['year', 'academic year', 'academic_year'],
                        'board': ['board', 'boards', 'board_name'],
                        'subject': ['subject', 'course', 'subjects'],
                        'mean': ['mean', 'average', 'avg'],
                        'sd': ['sd', 'std dev', 'standard deviation', 'std_dev']
                    }

                    for standard, variants in column_mapping.items():
                        for variant in variants:
                            if variant in df.columns:
                                df.rename(columns={variant: standard}, inplace=True)
                                break

                    required_columns = {'year', 'board', 'subject', 'mean', 'sd'}
                    if not required_columns.issubset(df.columns):
                        missing = required_columns - set(df.columns)
                        self.message_user(
                            request,
                            f"Missing required columns: {', '.join(missing)}",
                            level='error'
                        )
                        return redirect("..")

                    success_count = 0
                    errors = []

                    for index, row in df.iterrows():
                        try:
                            year_val = int(str(row['year']).strip())
                            board_name = str(row['board']).strip()
                            subject = str(row['subject']).strip().title()
                            mean = float(str(row['mean']).strip())
                            sd = float(str(row['sd']).strip())

                            if sd <= 0:
                                errors.append(f"Row {index + 2}: SD must be positive (was {sd})")
                                continue

                            year_obj, _ = Year.objects.get_or_create(value=year_val)
                            board_obj, _ = Board.objects.get_or_create(
                                name=board_name,
                                year=year_obj,
                                defaults={'name': board_name, 'year': year_obj}
                            )

                            _, created = SubjectStat.objects.update_or_create(
                                board=board_obj,
                                subject__iexact=subject,
                                defaults={'mean': mean, 'sd': sd}
                            )

                            success_count += 1
                            action = "Created" if created else "Updated"
                            logger.info(f"{action} stats for {board_name} - {subject} ({year_val})")

                        except Exception as e:
                            error_msg = f"Row {index + 2}: {str(e)}"
                            errors.append(error_msg)
                            logger.error(error_msg)

                    if success_count:
                        msg = f"Successfully processed {success_count} records"
                        level = 'success'
                    else:
                        msg = "No records processed"
                        level = 'warning'

                    if errors:
                        msg += f" with {len(errors)} errors"
                        level = 'warning' if success_count else 'error'

                    self.message_user(request, msg, level=level)

                    for error in errors[:5]:
                        self.message_user(request, error, level='error')

                    return redirect("..")

                except Exception as e:
                    tb = traceback.format_exc()
                    logger.error(f"Upload error: {e}\n{tb}")
                    self.message_user(
                        request,
                        f"File processing error: {str(e)}",
                        level='error'
                    )
        else:
            form = UploadStatsForm()

        return render(request, "admin/upload_stats.html", {
            "form": form,
            "title": "Upload Subject Statistics",
            "opts": self.model._meta,
        })

# Register the models
admin.site.register(Year, YearAdmin)
admin.site.register(Board, BoardAdmin)