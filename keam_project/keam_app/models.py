from django.db import models

# models.py

class Year(models.Model):
    value = models.PositiveIntegerField(unique=True)

    def __str__(self):
        return str(self.value)


class Board(models.Model):
    name = models.CharField(max_length=100)
    year = models.ForeignKey(Year, on_delete=models.CASCADE, default=1)


    def __str__(self):
        return f"{self.name} ({self.year})"


class SubjectStat(models.Model):
    board = models.ForeignKey(Board, on_delete=models.CASCADE)
    subject = models.CharField(max_length=50)
    mean = models.FloatField()
    sd = models.FloatField()

    def __str__(self):
        return f"{self.board.name} - {self.subject}"




