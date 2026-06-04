Set WshShell = CreateObject("WScript.Shell")
WshShell.Environment("Process").Item("PATH") = "C:\Users\Pichau\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin;" & WshShell.Environment("Process").Item("PATH")
WshShell.CurrentDirectory = "C:\Users\Pichau\Documents\Dev\fast"
WshShell.Run "pythonw -m meeting_processor serve", 0, False
