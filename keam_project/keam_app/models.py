from django.db import models

class Year(models.Model):
    value = models.PositiveIntegerField(unique=True)

    def __str__(self):
        return str(self.value)

    class Meta:
        ordering = ['-value']
        verbose_name = "Academic Year"
        verbose_name_plural = "Academic Years"


class Board(models.Model):
    name = models.CharField(max_length=100)
    year = models.ForeignKey(Year, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.name} ({self.year})"

    class Meta:
        ordering = ['year', 'name']
        unique_together = ('name', 'year')  # Prevent duplicate boards for same year


class SubjectStat(models.Model):
    board = models.ForeignKey(Board, on_delete=models.CASCADE)
    subject = models.CharField(max_length=50)
    mean = models.FloatField()
    sd = models.FloatField()

    def __str__(self):
        return f"{self.board.name} - {self.subject}"

    class Meta:
        ordering = ['board__year', 'board__name', 'subject']
        verbose_name = "Subject Statistics"
        verbose_name_plural = "Subject Statistics"