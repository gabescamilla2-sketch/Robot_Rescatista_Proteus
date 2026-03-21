import pygame
import math
import time
import numpy as np
from collections import deque
from rd03d import RD03D

class RadarDisplay:
    def __init__(self, width=1200, height=900):
        pygame.init()
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("mmWave Radar Display - Respiration Detection")
        
        # Colors
        self.BLACK = (0, 0, 0)
        self.GREEN = (0, 255, 0)
        self.DARK_GREEN = (0, 100, 0)
        self.BRIGHT_GREEN = (0, 255, 100)
        self.RED = (255, 0, 0)
        self.YELLOW = (255, 255, 0)
        self.WHITE = (255, 255, 255)
        self.GRAY = (128, 128, 128)
        self.BLUE = (0, 100, 255)
        self.CYAN = (0, 255, 255)
        
        # Radar settings
        self.info_panel_width = 200
        self.radar_area_width = width - self.info_panel_width - 40
        self.radar_area_height = height - 100
        
        # Calculate radar position and size
        self.center_x = self.info_panel_width + self.radar_area_width // 2
        self.center_y = height - 80
        
        max_radius_by_width = self.radar_area_width // 2 - 20
        max_radius_by_height = self.radar_area_height - 60
        self.radar_radius = min(max_radius_by_width, max_radius_by_height)
        
        self.max_range = 7000  # 7 meters in mm
        self.fov_angle = 120  # 120 degree field of view
        
        # Font for text
        self.font = pygame.font.Font(None, 24)
        self.small_font = pygame.font.Font(None, 18)
        self.large_font = pygame.font.Font(None, 32)
        
        # Sweep animation
        self.sweep_angle = 0
        self.sweep_speed = 2
        
        # Respiration detection
        self.respiration_data = {}  # Store respiration data for each target
        self.respiration_history_length = 100  # Number of samples to keep
        self.breathing_threshold = 0.5  # Threshold for breathing detection (cm/s)
        
    def set_max_range(self, range_meters):
        """Set the maximum range in meters"""
        self.max_range = range_meters * 1000
        
    def distance_to_pixels(self, distance_mm):
        """Convert distance in mm to pixel radius"""
        return int((distance_mm / self.max_range) * self.radar_radius)
    
    def angle_to_screen_angle(self, angle_deg):
        """Convert radar angle to screen angle (radar faces up)"""
        return -angle_deg + 90
    
    def polar_to_cartesian(self, distance_mm, angle_deg):
        """Convert polar coordinates to screen cartesian"""
        pixel_radius = self.distance_to_pixels(distance_mm)
        screen_angle = math.radians(self.angle_to_screen_angle(angle_deg))
        
        x = self.center_x + pixel_radius * math.cos(screen_angle)
        y = self.center_y - pixel_radius * math.sin(screen_angle)
        
        return int(x), int(y)
    
    def update_respiration_data(self, target_num, speed):
        """Update respiration data for a target"""
        if target_num not in self.respiration_data:
            self.respiration_data[target_num] = {
                'speed_history': deque(maxlen=self.respiration_history_length),
                'breathing_detected': False,
                'breathing_rate': 0,
                'last_update': time.time()
            }
        
        data = self.respiration_data[target_num]
        data['speed_history'].append(speed)
        
        # Analyze breathing pattern (every 2 seconds)
        current_time = time.time()
        if current_time - data['last_update'] >= 2.0 and len(data['speed_history']) > 10:
            self.analyze_breathing(target_num)
            data['last_update'] = current_time
    
    def analyze_breathing(self, target_num):
        """Analyze speed data to detect breathing patterns"""
        if target_num not in self.respiration_data:
            return
        
        data = self.respiration_data[target_num]
        speed_history = list(data['speed_history'])
        
        if len(speed_history) < 10:
            return
        
        # Calculate speed variations (breathing causes small periodic speed changes)
        speed_variations = np.abs(np.diff(speed_history))
        avg_variation = np.mean(speed_variations)
        
        # Detect breathing based on speed variations
        data['breathing_detected'] = avg_variation > self.breathing_threshold
        
        # Simple breathing rate estimation (breaths per minute)
        if data['breathing_detected']:
            # Count zero crossings as a simple breathing rate estimator
            zero_crossings = np.where(np.diff(np.array(speed_history) > 0))[0]
            if len(zero_crossings) > 1:
                breath_intervals = np.diff(zero_crossings)
                avg_interval = np.mean(breath_intervals) if len(breath_intervals) > 0 else 0
                if avg_interval > 0:
                    data['breathing_rate'] = (60 / avg_interval) * 0.5  # Adjust for sample rate
                else:
                    data['breathing_rate'] = 0
            else:
                data['breathing_rate'] = 12  # Default normal breathing rate
        else:
            data['breathing_rate'] = 0
    
    def draw_range_arc(self, radius, start_angle, end_angle, color, width=1):
        """Draw an arc for range circles within the FOV"""
        if radius <= 0 or radius > self.radar_radius:
            return
            
        start_screen_angle = math.radians(self.angle_to_screen_angle(start_angle))
        end_screen_angle = math.radians(self.angle_to_screen_angle(end_angle))
        
        points = []
        angle_step = (end_screen_angle - start_screen_angle) / 50
        
        for i in range(51):
            angle = start_screen_angle + i * angle_step
            x = self.center_x + radius * math.cos(angle)
            y = self.center_y - radius * math.sin(angle)
            points.append((x, y))
        
        if len(points) > 1:
            pygame.draw.lines(self.screen, color, False, points, width)
    
    def draw_radar_background(self):
        """Draw the radar display background"""
        self.screen.fill(self.BLACK)
        
        fov_half = self.fov_angle / 2
        max_range_meters = self.max_range / 1000
        
        # Dynamic range intervals
        if max_range_meters <= 5:
            range_intervals = list(range(1, int(max_range_meters) + 1))
        elif max_range_meters <= 10:
            range_intervals = list(range(2, int(max_range_meters) + 1, 2))
        else:
            range_intervals = list(range(5, int(max_range_meters) + 1, 5))
        
        for range_m in range_intervals:
            range_mm = range_m * 1000
            radius = self.distance_to_pixels(range_mm)
            if 0 < radius <= self.radar_radius:
                self.draw_range_arc(radius, -fov_half, fov_half, self.DARK_GREEN)
                
                label_angle = 0
                screen_angle = math.radians(self.angle_to_screen_angle(label_angle))
                label_x = self.center_x + (radius + 15) * math.cos(screen_angle)
                label_y = self.center_y - (radius + 15) * math.sin(screen_angle)
                
                label = self.small_font.render(f"{range_m}m", True, self.DARK_GREEN)
                label_rect = label.get_rect(center=(label_x, label_y))
                self.screen.blit(label, label_rect)
        
        # Draw field of view boundary lines
        for angle in [-fov_half, fov_half]:
            screen_angle = math.radians(self.angle_to_screen_angle(angle))
            end_x = self.center_x + self.radar_radius * math.cos(screen_angle)
            end_y = self.center_y - self.radar_radius * math.sin(screen_angle)
            pygame.draw.line(self.screen, self.GREEN, 
                           (self.center_x, self.center_y), (end_x, end_y), 2)
        
        # Draw angle lines every 30 degrees within FOV
        for angle in range(-60, 61, 30):
            if abs(angle) <= fov_half and angle != 0:
                screen_angle = math.radians(self.angle_to_screen_angle(angle))
                end_x = self.center_x + self.radar_radius * math.cos(screen_angle)
                end_y = self.center_y - self.radar_radius * math.sin(screen_angle)
                pygame.draw.line(self.screen, self.DARK_GREEN, 
                               (self.center_x, self.center_y), (end_x, end_y), 1)
                
                label_x = self.center_x + (self.radar_radius + 25) * math.cos(screen_angle)
                label_y = self.center_y - (self.radar_radius + 25) * math.sin(screen_angle)
                label = self.small_font.render(f"{angle}°", True, self.DARK_GREEN)
                label_rect = label.get_rect(center=(label_x, label_y))
                self.screen.blit(label, label_rect)
        
        # Draw center line (0 degrees)
        screen_angle = math.radians(self.angle_to_screen_angle(0))
        end_x = self.center_x + self.radar_radius * math.cos(screen_angle)
        end_y = self.center_y - self.radar_radius * math.sin(screen_angle)
        pygame.draw.line(self.screen, self.GREEN, 
                       (self.center_x, self.center_y), (end_x, end_y), 1)
        
        # Draw center point
        pygame.draw.circle(self.screen, self.GREEN, (self.center_x, self.center_y), 4)
        
        # Draw radar area outline
        fov_half_rad = math.radians(fov_half)
        left_angle = math.radians(self.angle_to_screen_angle(-fov_half))
        right_angle = math.radians(self.angle_to_screen_angle(fov_half))
        
        arc_points = [(self.center_x, self.center_y)]
        for i in range(51):
            angle = left_angle + i * (right_angle - left_angle) / 50
            x = self.center_x + self.radar_radius * math.cos(angle)
            y = self.center_y - self.radar_radius * math.sin(angle)
            arc_points.append((x, y))
        arc_points.append((self.center_x, self.center_y))
        
        pygame.draw.polygon(self.screen, self.DARK_GREEN, arc_points, 1)
    
    def draw_sweep(self):
        """Draw rotating sweep line"""
        fov_half = self.fov_angle / 2
        if abs(self.sweep_angle) <= fov_half:
            screen_angle = math.radians(self.angle_to_screen_angle(self.sweep_angle))
            end_x = self.center_x + self.radar_radius * math.cos(screen_angle)
            end_y = self.center_y - self.radar_radius * math.sin(screen_angle)
            
            for i in range(5):
                alpha_angle = self.sweep_angle - i * 3
                if abs(alpha_angle) <= fov_half:
                    alpha_screen_angle = math.radians(self.angle_to_screen_angle(alpha_angle))
                    alpha_end_x = self.center_x + self.radar_radius * math.cos(alpha_screen_angle)
                    alpha_end_y = self.center_y - self.radar_radius * math.sin(alpha_screen_angle)
                    
                    color_intensity = 255 - (i * 40)
                    if color_intensity > 0:
                        color = (0, color_intensity, 0)
                        pygame.draw.line(self.screen, color, 
                                       (self.center_x, self.center_y), 
                                       (alpha_end_x, alpha_end_y), max(1, 3-i))
        
        self.sweep_angle += self.sweep_speed
        if self.sweep_angle > fov_half:
            self.sweep_angle = -fov_half
    
    def draw_target(self, target, target_num):
        """Draw a target with speed arrow and breathing indicator"""
        if target.distance > self.max_range:
            return
        
        if abs(target.angle) > self.fov_angle / 2:
            return
        
        x, y = self.polar_to_cartesian(target.distance, target.angle)
        
        # Update respiration data
        self.update_respiration_data(target_num, target.speed)
        
        # Target colors based on breathing status
        if target_num in self.respiration_data and self.respiration_data[target_num]['breathing_detected']:
            color = self.CYAN  # Breathing detected - cyan
            pulse_color = self.BLUE
        else:
            color = self.YELLOW  # No breathing detected - yellow
            pulse_color = self.RED
        
        # Draw pulsing circle for breathing indication
        if target_num in self.respiration_data:
            data = self.respiration_data[target_num]
            if data['breathing_detected']:
                # Create pulsing effect for breathing
                pulse_size = 5 + 3 * math.sin(time.time() * 4)  # Pulsing animation
                pygame.draw.circle(self.screen, pulse_color, (x, y), int(8 + pulse_size), 2)
        
        # Draw target dot
        pygame.draw.circle(self.screen, color, (x, y), 8)
        pygame.draw.circle(self.screen, self.WHITE, (x, y), 8, 2)
        
        # Draw speed arrow
        if abs(target.speed) > 1:
            arrow_length = min(40, abs(target.speed) * 2)
            angle_rad = math.radians(self.angle_to_screen_angle(target.angle))
            
            if target.speed > 0:
                arrow_end_x = x + arrow_length * math.cos(angle_rad)
                arrow_end_y = y - arrow_length * math.sin(angle_rad)
                arrow_color = self.RED
            else:
                arrow_end_x = x - arrow_length * math.cos(angle_rad)
                arrow_end_y = y + arrow_length * math.sin(angle_rad)
                arrow_color = self.GREEN
            
            pygame.draw.line(self.screen, arrow_color, (x, y), (arrow_end_x, arrow_end_y), 3)
            
            arrow_angle = math.atan2(arrow_end_y - y, arrow_end_x - x)
            head_length = 10
            head1_x = arrow_end_x - head_length * math.cos(arrow_angle - 0.5)
            head1_y = arrow_end_y - head_length * math.sin(arrow_angle - 0.5)
            head2_x = arrow_end_x - head_length * math.cos(arrow_angle + 0.5)
            head2_y = arrow_end_y - head_length * math.sin(arrow_angle + 0.5)
            
            pygame.draw.polygon(self.screen, arrow_color, 
                              [(arrow_end_x, arrow_end_y), (head1_x, head1_y), (head2_x, head2_y)])
        
        # Target label with breathing indicator
        breathing_symbol = "💨" if (target_num in self.respiration_data and 
                                  self.respiration_data[target_num]['breathing_detected']) else "○"
        label_text = f"T{target_num+1} {breathing_symbol}"
        label = self.small_font.render(label_text, True, color)
        self.screen.blit(label, (x + 12, y - 12))
    
    def draw_respiration_graph(self, target_num, x, y, width=150, height=60):
        """Draw a small respiration graph for a target"""
        if target_num not in self.respiration_data:
            return
        
        data = self.respiration_data[target_num]
        speed_history = list(data['speed_history'])
        
        if len(speed_history) < 2:
            return
        
        # Draw graph background
        graph_rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, (30, 30, 30), graph_rect)
        pygame.draw.rect(self.screen, self.GRAY, graph_rect, 1)
        
        # Draw respiration waveform
        if len(speed_history) > 1:
            points = []
            max_speed = max(1, max(abs(s) for s in speed_history))
            
            for i, speed in enumerate(speed_history[-20:]):  # Last 20 samples
                x_pos = x + (i / 19) * (width - 10) + 5
                y_pos = y + height / 2 - (speed / max_speed) * (height / 2 - 5)
                points.append((x_pos, y_pos))
            
            if len(points) > 1:
                color = self.CYAN if data['breathing_detected'] else self.YELLOW
                pygame.draw.lines(self.screen, color, False, points, 2)
        
        # Draw graph label
        status = "BREATHING" if data['breathing_detected'] else "NO BREATHING"
        color = self.CYAN if data['breathing_detected'] else self.YELLOW
        label = self.small_font.render(f"T{target_num+1}: {status}", True, color)
        self.screen.blit(label, (x, y - 15))
        
        # Draw breathing rate if available
        if data['breathing_detected'] and data['breathing_rate'] > 0:
            rate_text = self.small_font.render(f"Rate: {data['breathing_rate']:.1f} bpm", True, self.WHITE)
            self.screen.blit(rate_text, (x, y + height + 2))
    
    def draw_info_panel(self, targets):
        """Draw information panel with respiration data"""
        panel_x = 10
        panel_y = 10
        
        # Draw panel background
        panel_rect = pygame.Rect(5, 5, self.info_panel_width - 10, self.height - 10)
        pygame.draw.rect(self.screen, (20, 20, 20), panel_rect)
        pygame.draw.rect(self.screen, self.DARK_GREEN, panel_rect, 2)
        
        # Title
        title = self.large_font.render("Radar - Respiration", True, self.WHITE)
        self.screen.blit(title, (panel_x, panel_y))
        subtitle = self.small_font.render("RD-03D Detection", True, self.GRAY)
        self.screen.blit(subtitle, (panel_x, panel_y + 25))
        
        # Range info
        range_text = self.small_font.render(f"Max Range: {self.max_range/1000:.1f}m", True, self.GRAY)
        self.screen.blit(range_text, (panel_x, panel_y + 50))
        
        # Target info
        y_offset = 80
        active_targets = 0
        
        for i, target in enumerate(targets[:3]):
            if target and target.distance <= self.max_range and abs(target.angle) <= 60:
                active_targets += 1
                
                # Determine color based on breathing status
                if i in self.respiration_data and self.respiration_data[i]['breathing_detected']:
                    color = self.CYAN
                    breathing_status = "BREATHING ✅"
                    breathing_rate = f"{self.respiration_data[i]['breathing_rate']:.1f} bpm"
                else:
                    color = self.YELLOW
                    breathing_status = "NO BREATHING ❌"
                    breathing_rate = "N/A"
                
                info_lines = [
                    f"Target {i+1}: {breathing_status}",
                    f"  Distance: {target.distance/1000:.2f}m",
                    f"  Angle: {target.angle:.1f}°",
                    f"  Speed: {target.speed:.1f} cm/s",
                    f"  Breath Rate: {breathing_rate}",
                ]
                
                for j, line in enumerate(info_lines):
                    text_color = color if j == 0 else self.WHITE
                    text = self.small_font.render(line, True, text_color)
                    self.screen.blit(text, (panel_x, panel_y + y_offset + j * 18))
                
                y_offset += 100
        
        if active_targets == 0:
            no_targets = self.small_font.render("No targets detected", True, self.GRAY)
            self.screen.blit(no_targets, (panel_x, panel_y + y_offset))
        
        # Draw respiration graphs for detected targets
        graph_y = self.height - 200
        for i, target in enumerate(targets[:3]):
            if target and target.distance <= self.max_range and abs(target.angle) <= 60:
                self.draw_respiration_graph(i, panel_x, graph_y)
                graph_y += 80
        
        # Legend
        legend_y = self.height - 60
        legend_title = self.small_font.render("Breathing Legend:", True, self.WHITE)
        self.screen.blit(legend_title, (panel_x, legend_y))
        
        # Breathing status legend
        pygame.draw.circle(self.screen, self.CYAN, (panel_x + 10, legend_y + 20), 6)
        breathing_text = self.small_font.render("Breathing Detected", True, self.WHITE)
        self.screen.blit(breathing_text, (panel_x + 25, legend_y + 15))
        
        pygame.draw.circle(self.screen, self.YELLOW, (panel_x + 10, legend_y + 40), 6)
        no_breath_text = self.small_font.render("No Breathing", True, self.WHITE)
        self.screen.blit(no_breath_text, (panel_x + 25, legend_y + 35))

def main():
    # Initialize radar
    radar = RD03D()
    radar.set_multi_mode(True)
    
    # Initialize display
    display = RadarDisplay(1200, 800)
    display.set_max_range(7)
    
    clock = pygame.time.Clock()
    
    print("Radar respiration detection started. Close window to exit.")
    print("Features:")
    print("- Real-time breathing detection")
    print("- Breathing rate estimation")
    print("- Visual breathing indicators")
    print("- Respiration waveform graphs")
    print("")
    print("Instructions:")
    print("- Stand 1-3 meters in front of the radar")
    print("- Stay relatively still for breathing detection")
    print("- Move slowly to test speed arrows")
    print("- Close window or press ESC to exit")
    
    try:
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_r:
                        # Reset radar range
                        display.set_max_range(7)
                        print("Range reset to 7 meters")
                    elif event.key == pygame.K_UP:
                        # Increase range
                        current_range = display.max_range / 1000
                        new_range = min(10, current_range + 1)
                        display.set_max_range(new_range)
                        print(f"Range increased to {new_range} meters")
                    elif event.key == pygame.K_DOWN:
                        # Decrease range
                        current_range = display.max_range / 1000
                        new_range = max(3, current_range - 1)
                        display.set_max_range(new_range)
                        print(f"Range decreased to {new_range} meters")
            
            # Update radar data
            radar.update()
            targets = [radar.get_target(1), radar.get_target(2), radar.get_target(3)]
            
            # Draw everything
            display.draw_radar_background()
            display.draw_sweep()
            
            # Draw targets
            for i, target in enumerate(targets):
                if target:
                    display.draw_target(target, i)
            
            display.draw_info_panel(targets)
            
            # Update display
            pygame.display.flip()
            clock.tick(30)
    
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")
    finally:
        radar.close()
        pygame.quit()
        print("Radar respiration detection stopped.")

if __name__ == "__main__":
    main()